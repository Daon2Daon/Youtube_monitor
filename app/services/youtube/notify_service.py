"""
YouTube 알림 발송 서비스 (독립 앱 버전).

- 예약발송: APScheduler Cron `youtube_notify_HHMM`
- 즉시발송+야간제한 보정: Cron `youtube_immediate_catchup` (quiet_hours_end + 5분)
"""

from __future__ import annotations

import asyncio
import time
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.youtube_channel import YoutubeChannel
from app.models.youtube_video import YoutubeVideo

CATCHUP_LOG_PREFIX = "youtube_immediate_catchup"
SCHEDULED_LOG_PREFIX = "youtube_scheduled_notify"


async def _fetch_pending_notify_pks(session_factory: async_sessionmaker) -> List[int]:
    """미발송·분석완료 영상 video_pk (notify_enabled 채널, 오래된 순)."""
    async with session_factory() as sess:
        stmt = (
            select(YoutubeVideo.video_pk)
            .join(YoutubeChannel, YoutubeVideo.channel_pk == YoutubeChannel.channel_pk)
            .where(YoutubeVideo.analysis_status == "done")
            .where(YoutubeVideo.notified_at.is_(None))
            .where(YoutubeChannel.notify_enabled.is_(True))
            .order_by(YoutubeVideo.published_at.asc())
        )
        result = await sess.execute(stmt)
        return list(result.scalars().all())


async def _log_disabled_channel_pending(session_factory: async_sessionmaker, log_prefix: str) -> None:
    async with session_factory() as sess:
        diag_stmt = (
            select(YoutubeVideo.video_pk)
            .join(YoutubeChannel, YoutubeVideo.channel_pk == YoutubeChannel.channel_pk)
            .where(YoutubeVideo.analysis_status == "done")
            .where(YoutubeVideo.notified_at.is_(None))
            .where(YoutubeChannel.notify_enabled.is_(False))
        )
        diag_result = await sess.execute(diag_stmt)
        disabled_pks = list(diag_result.scalars().all())
    if disabled_pks:
        print(
            f"ℹ️  {log_prefix}: 알림 비활성 채널 미발송 영상 {len(disabled_pks)}건 존재"
            " (채널 notify_enabled=FALSE) — 발송 제외"
        )


async def _send_pending_notifications(
    session_factory: async_sessionmaker,
    *,
    log_prefix: str,
    batch_log_label: str,
    max_per: int,
    wait_sec: int,
    threshold: float,
) -> None:
    """미발송 영상을 순차 Telegram 발송 (공통 코어)."""
    from app.services.youtube.youtube_bot import youtube_bot

    all_pending_pks = await _fetch_pending_notify_pks(session_factory)
    await _log_disabled_channel_pending(session_factory, log_prefix)

    if not all_pending_pks:
        print(f"ℹ️  {log_prefix}: 미발송 영상 없음 (notify_enabled=TRUE 채널 기준)")
        return

    if max_per < 1:
        max_per = 1
    elif max_per > 50:
        max_per = 50

    video_pks = all_pending_pks[:max_per]
    remaining = len(all_pending_pks) - len(video_pks)

    print(
        f"📤 {log_prefix}: 이번 회차 {len(video_pks)}건 발송 "
        f"(대기 {wait_sec}초/건, 회당 상한 {max_per}건"
        f"{f', 잔여 미발송 약 {remaining}건은 다음 회차' if remaining > 0 else ''})"
    )
    sent = 0
    t_batch = time.monotonic()

    for i, pk in enumerate(video_pks):
        try:
            ok = await youtube_bot.notify_standalone(
                session_factory=session_factory,
                video_pk=pk,
                low_confidence_threshold=threshold,
            )
            if ok:
                sent += 1
        except Exception as exc:
            print(f"⚠️  {log_prefix}: video_pk={pk} 발송 실패 — {exc}")

        if i < len(video_pks) - 1 and wait_sec > 0:
            await asyncio.sleep(wait_sec)

    print(f"✅ {log_prefix}: {sent}/{len(video_pks)}건 발송 완료 (이번 회차)")

    from app.services.youtube.job_logger import (
        JOB_TYPE_NOTIFY,
        _STATUS_FAIL,
        _STATUS_SUCCESS,
        write_job_log,
    )

    batch_ms = int((time.monotonic() - t_batch) * 1000)
    batch_msg = (
        f"{batch_log_label}: {sent}/{len(video_pks)}건 성공"
        + (f", 잔여 대기 약 {remaining}건" if remaining else "")
    )
    await write_job_log(
        session_factory,
        job_type=JOB_TYPE_NOTIFY,
        status=_STATUS_SUCCESS if sent > 0 else _STATUS_FAIL,
        message=batch_msg,
        duration_ms=batch_ms,
    )


def _notification_send_limits(notif_cfg) -> tuple[int, int, float]:
    max_per = int(notif_cfg.scheduled_max_per_run or 5)
    wait_sec = int(notif_cfg.wait_between_messages_sec or 30)
    threshold = float(notif_cfg.low_confidence_threshold or 0.5)
    return max_per, wait_sec, threshold


async def _youtube_scheduled_notify_async() -> None:
    from app.services.youtube.db_engine import db_engine_manager
    from app.services.youtube.settings_manager import get_youtube_settings_manager

    mgr = get_youtube_settings_manager()
    notif_cfg = mgr.get_notification()

    if not notif_cfg.telegram_enabled:
        print(f"ℹ️  {SCHEDULED_LOG_PREFIX}: Telegram 알림 비활성 — skip")
        return

    if notif_cfg.send_mode != "scheduled":
        print(f"ℹ️  {SCHEDULED_LOG_PREFIX}: 즉시발송 모드 — 예약잡은 실행하지 않음")
        return

    try:
        engine = await db_engine_manager.get_engine()
    except Exception as exc:
        print(f"⚠️  {SCHEDULED_LOG_PREFIX}: DB 연결 실패 — {exc}")
        return

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    max_per, wait_sec, threshold = _notification_send_limits(notif_cfg)

    await _send_pending_notifications(
        session_factory,
        log_prefix=SCHEDULED_LOG_PREFIX,
        batch_log_label="예약발송 회차",
        max_per=max_per,
        wait_sec=wait_sec,
        threshold=threshold,
    )


async def _youtube_immediate_catchup_async() -> None:
    """즉시발송 모드에서 야간 제한으로 skip된 미발송 영상 보정 발송."""
    from app.services.youtube.db_engine import db_engine_manager
    from app.services.youtube.quiet_hours import (
        is_quiet_hours_now,
        quiet_hours_label,
    )
    from app.services.youtube.settings_manager import get_youtube_settings_manager

    mgr = get_youtube_settings_manager()
    notif_cfg = mgr.get_notification()

    if not notif_cfg.telegram_enabled:
        print(f"ℹ️  {CATCHUP_LOG_PREFIX}: Telegram 알림 비활성 — skip")
        return

    if notif_cfg.send_mode != "immediate":
        print(f"ℹ️  {CATCHUP_LOG_PREFIX}: 예약발송 모드 — 보정잡은 실행하지 않음")
        return

    if not notif_cfg.quiet_hours_enabled:
        print(f"ℹ️  {CATCHUP_LOG_PREFIX}: 야간 알림 제한 비활성 — 보정잡 skip")
        return

    if is_quiet_hours_now(
        notif_cfg.quiet_hours_enabled,
        notif_cfg.quiet_hours_start,
        notif_cfg.quiet_hours_end,
    ):
        label = quiet_hours_label(notif_cfg.quiet_hours_start, notif_cfg.quiet_hours_end)
        print(f"ℹ️  {CATCHUP_LOG_PREFIX}: 아직 제한 시간대({label}) — skip")
        return

    try:
        engine = await db_engine_manager.get_engine()
    except Exception as exc:
        print(f"⚠️  {CATCHUP_LOG_PREFIX}: DB 연결 실패 — {exc}")
        return

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    max_per, wait_sec, threshold = _notification_send_limits(notif_cfg)

    await _send_pending_notifications(
        session_factory,
        log_prefix=CATCHUP_LOG_PREFIX,
        batch_log_label="야간제한 보정 발송",
        max_per=max_per,
        wait_sec=wait_sec,
        threshold=threshold,
    )


def youtube_scheduled_notify_sync() -> None:
    """APScheduler CronTrigger 잡에서 호출되는 동기 래퍼 (예약발송)."""
    asyncio.run(_youtube_scheduled_notify_async())


def youtube_immediate_catchup_sync() -> None:
    """APScheduler CronTrigger 잡에서 호출되는 동기 래퍼 (즉시발송 야간 보정)."""
    asyncio.run(_youtube_immediate_catchup_async())
