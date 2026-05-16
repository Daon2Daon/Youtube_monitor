"""
YouTube 모니터 알림 봇 (독립 앱 버전).

분석 완료된 영상의 요약을 Telegram HTML 포맷으로 포매팅해 발송한다.
telegram_chat_id는 youtube_settings.notification 테이블에서 조회한다.

발송 포맷 (명세 4.4.1):
    <b>🎬 [{channel_name}] 신규 영상</b>

    <b>{headline}</b>

    {full_analysis_md}  (HTML 이스케이프된 본문)

    {bullet_points}  (각 항목 • + 이스케이프)

    🏷 {tags_joined}
    📅 {published_at_kst}  ·  ⏱ {duration_human}

    🔗 <a href="{video_url}">영상 보러가기</a>
"""

from __future__ import annotations

import html
import time
from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import select, update

from app.models.youtube_channel import YoutubeChannel
from app.models.youtube_tag import YoutubeTag
from app.models.youtube_video import YoutubeVideo
from app.models.youtube_video_analysis import YoutubeVideoAnalysis
from app.models.youtube_video_tag import YoutubeVideoTag
from app.services.notification.telegram_sender import telegram_sender
from app.services.youtube.job_logger import (
    JOB_TYPE_NOTIFY,
    write_job_log,
    _STATUS_FAIL,
    _STATUS_SKIP,
    _STATUS_SUCCESS,
)

# Telegram 메시지 최대 글자 수
_TELEGRAM_MAX_LEN = 4096


def _to_kst(dt: datetime) -> str:
    try:
        from zoneinfo import ZoneInfo

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        kst = dt.astimezone(ZoneInfo("Asia/Seoul"))
        return kst.strftime("%Y-%m-%d %H:%M KST")
    except Exception:
        return str(dt)


def _format_duration(seconds: Optional[int]) -> str:
    if not seconds:
        return ""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _truncate_html(text: str, max_len: int, suffix: str = "...") -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - len(suffix)] + suffix


def _escape(s: str) -> str:
    """HTML 특수문자 이스케이프 (plain text 영역용)."""
    return html.escape(s or "")


def _escape_href(url: str) -> str:
    """href=\"...\" 안에 넣을 URL용 이스케이프 (&, 따옴표 등). Telegram HTML 파서 오류 방지."""
    return html.escape((url or "").strip(), quote=True)


def _format_bullet_points(bullet_points: Optional[Any]) -> str:
    """JSON bullet_points(문자열 리스트 등)를 Telegram HTML용 한 줄씩 포맷."""
    if not bullet_points or not isinstance(bullet_points, list):
        return ""
    out: List[str] = []
    for item in bullet_points:
        if item is None:
            continue
        s = str(item).strip()
        if s:
            out.append(f"• {_escape(s)}")
    return "\n".join(out)


def build_notification_text(
    channel_name: str,
    headline: Optional[str],
    full_analysis_md: str,
    bullet_points: Optional[Any],
    tags: List[str],
    published_at: datetime,
    duration_seconds: Optional[int],
    video_url: str,
    confidence_score: Optional[float] = None,
    low_confidence_threshold: float = 0.5,
) -> str:
    """명세 4.4.1 포맷으로 Telegram HTML 메시지 생성."""
    lines: List[str] = []

    # 저신뢰도 배지
    if confidence_score is not None and confidence_score < low_confidence_threshold:
        lines.append("⚠️ <b>[저신뢰도 분석]</b>")
        lines.append("")

    lines.append(f"<b>🎬 [{_escape(channel_name)}] 신규 영상</b>")
    lines.append("")

    if headline:
        lines.append(f"<b>{_escape(headline)}</b>")
        lines.append("")

    body_analysis = _escape(full_analysis_md or "")
    if body_analysis:
        lines.append(body_analysis)
        lines.append("")

    body_bullets = _format_bullet_points(bullet_points)
    if body_bullets:
        lines.append(body_bullets)
        lines.append("")

    if tags:
        lines.append(f"🏷 {', '.join(_escape(t) for t in tags)}")

    meta_parts: List[str] = [f"📅 {_to_kst(published_at)}"]
    dur = _format_duration(duration_seconds)
    if dur:
        meta_parts.append(f"⏱ {dur}")
    lines.append("  ·  ".join(meta_parts))
    lines.append("")

    lines.append(f'🔗 <a href="{_escape_href(video_url)}">영상 보러가기</a>')

    text = "\n".join(lines)

    # 4096자 초과 시 본문(full_analysis_md) 절단 → 그래도 초과 시 bullet 항목 수 축소
    if len(text) > _TELEGRAM_MAX_LEN:
        overflow = len(text) - _TELEGRAM_MAX_LEN + 50
        raw = full_analysis_md or ""
        if len(raw) > overflow:
            cut = len(raw) - overflow
            truncated_raw = raw[:cut] + "…"
            return build_notification_text(
                channel_name=channel_name,
                headline=headline,
                full_analysis_md=truncated_raw,
                bullet_points=bullet_points,
                tags=tags,
                published_at=published_at,
                duration_seconds=duration_seconds,
                video_url=video_url,
                confidence_score=confidence_score,
                low_confidence_threshold=low_confidence_threshold,
            )
        b_list = bullet_points if isinstance(bullet_points, list) else []
        if b_list:
            return build_notification_text(
                channel_name=channel_name,
                headline=headline,
                full_analysis_md="",
                bullet_points=b_list[:-1],
                tags=tags,
                published_at=published_at,
                duration_seconds=duration_seconds,
                video_url=video_url,
                confidence_score=confidence_score,
                low_confidence_threshold=low_confidence_threshold,
            )
        return _truncate_html(text, _TELEGRAM_MAX_LEN)

    return text


async def _write_notify_job_log(
    *,
    channel_pk: Optional[int],
    video_pk: Optional[int],
    status: str,
    message: str,
    duration_ms: int,
) -> None:
    """job_logs 테이블에 notify 잡 기록."""
    try:
        from app.services.youtube.db_engine import db_engine_manager

        engine = await db_engine_manager.get_engine()
        factory = async_sessionmaker(engine, expire_on_commit=False)
        await write_job_log(
            factory,
            job_type=JOB_TYPE_NOTIFY,
            status=status,
            message=message,
            duration_ms=duration_ms,
            channel_pk=channel_pk,
            video_pk=video_pk,
        )
    except Exception as exc:
        print(f"⚠️  YoutubeBot notify job_log 기록 실패: {exc}")


class YoutubeBot:
    """YouTube 영상 알림 발송 봇."""

    async def notify_standalone(
        self,
        session_factory: async_sessionmaker,
        video_pk: int,
        low_confidence_threshold: float = 0.5,
    ) -> bool:
        """DB 트랜잭션과 Telegram 네트워크 호출을 분리한 단건 발송.

        Phase 1 (트랜잭션): 영상·채널·분석 데이터 읽기
        Phase 2 (트랜잭션 밖): Telegram API 호출
        Phase 3 (트랜잭션): notified_at 갱신 및 job_log 기록
        """
        t0 = time.monotonic()

        def elapsed_ms() -> int:
            return int((time.monotonic() - t0) * 1000)

        # ── Phase 1: DB 읽기 ────────────────────────────────────────
        video_data: Optional[dict] = None

        async with session_factory() as sess:
            async with sess.begin():
                video = await self._fetch_video(sess, video_pk)
                if not video:
                    print(f"⚠️  YoutubeBot: video_pk={video_pk} 를 찾을 수 없습니다.")
                    await _write_notify_job_log(
                        channel_pk=None, video_pk=video_pk,
                        status=_STATUS_FAIL, message="영상 행 없음",
                        duration_ms=elapsed_ms(),
                    )
                    return False

                if video.notified_at is not None:
                    await _write_notify_job_log(
                        channel_pk=video.channel_pk, video_pk=video_pk,
                        status=_STATUS_SKIP, message="이미 발송됨 (notified_at)",
                        duration_ms=elapsed_ms(),
                    )
                    return True

                channel = await self._fetch_channel(sess, video.channel_pk)
                if channel and not channel.notify_enabled:
                    await _write_notify_job_log(
                        channel_pk=video.channel_pk, video_pk=video_pk,
                        status=_STATUS_SKIP, message="채널 알림 비활성 (notify_enabled)",
                        duration_ms=elapsed_ms(),
                    )
                    return False

                analysis = await self._fetch_analysis(sess, video_pk)
                if not analysis:
                    print(f"⚠️  YoutubeBot: video_pk={video_pk} 분석 결과 없음 — 발송 skip")
                    await _write_notify_job_log(
                        channel_pk=video.channel_pk, video_pk=video_pk,
                        status=_STATUS_SKIP, message="분석 결과 없음",
                        duration_ms=elapsed_ms(),
                    )
                    return False

                tags = await self._fetch_tag_names(sess, video_pk)

                video_data = {
                    "channel_pk": video.channel_pk,
                    "display_channel": (
                        video.source_channel_name
                        or (channel.channel_name if channel else "YouTube")
                    ),
                    "headline": analysis.headline,
                    "full_analysis_md": analysis.full_analysis_md or "",
                    "bullet_points": analysis.bullet_points,
                    "tags": tags,
                    "published_at": video.published_at,
                    "duration_seconds": video.duration_seconds,
                    "video_url": video.video_url,
                    "confidence_score": analysis.confidence_score,
                    "title_hint": (video.title or "")[:120],
                }

        assert video_data is not None

        # ── Phase 2: 메시지 빌드 및 사용자·Telegram 확인 ──────────────
        text_msg = build_notification_text(
            channel_name=video_data["display_channel"],
            headline=video_data["headline"],
            full_analysis_md=video_data["full_analysis_md"],
            bullet_points=video_data["bullet_points"],
            tags=video_data["tags"],
            published_at=video_data["published_at"],
            duration_seconds=video_data["duration_seconds"],
            video_url=video_data["video_url"],
            confidence_score=video_data["confidence_score"],
            low_confidence_threshold=low_confidence_threshold,
        )

        user = await self._get_user()
        if not user or not telegram_sender.is_available(user):
            print("⚠️  YoutubeBot: Telegram chat_id 없음 — 발송 skip")
            await _write_notify_job_log(
                channel_pk=video_data["channel_pk"], video_pk=video_pk,
                status=_STATUS_SKIP, message="Telegram chat_id 없음",
                duration_ms=elapsed_ms(),
            )
            return False

        # ── Telegram 발송 (트랜잭션 밖) ─────────────────────────────
        ok = await telegram_sender.send_message(user, text_msg)

        # ── Phase 3: DB 쓰기 ────────────────────────────────────────
        title_hint = video_data["title_hint"]
        channel_pk_val = video_data["channel_pk"]

        async with session_factory() as sess:
            async with sess.begin():
                if ok:
                    await sess.execute(
                        update(YoutubeVideo)
                        .where(YoutubeVideo.video_pk == video_pk)
                        .values(notified_at=datetime.now(timezone.utc))
                    )
                    await _write_notify_job_log(
                        channel_pk=channel_pk_val, video_pk=video_pk,
                        status=_STATUS_SUCCESS,
                        message=f"Telegram 발송 완료: {title_hint}",
                        duration_ms=elapsed_ms(),
                    )
                else:
                    await _write_notify_job_log(
                        channel_pk=channel_pk_val, video_pk=video_pk,
                        status=_STATUS_FAIL,
                        message=f"Telegram sendMessage 실패: {title_hint}",
                        duration_ms=elapsed_ms(),
                    )

        return ok

    # ── 내부 조회 헬퍼 ──────────────────────────────────────────────────────

    async def _fetch_video(
        self, session: AsyncSession, video_pk: int
    ) -> Optional[YoutubeVideo]:
        stmt = select(YoutubeVideo).where(YoutubeVideo.video_pk == video_pk)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _fetch_analysis(
        self, session: AsyncSession, video_pk: int
    ) -> Optional[YoutubeVideoAnalysis]:
        stmt = select(YoutubeVideoAnalysis).where(
            YoutubeVideoAnalysis.video_pk == video_pk
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _fetch_channel(
        self, session: AsyncSession, channel_pk: int
    ) -> Optional[YoutubeChannel]:
        stmt = select(YoutubeChannel).where(YoutubeChannel.channel_pk == channel_pk)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _fetch_tag_names(
        self, session: AsyncSession, video_pk: int
    ) -> List[str]:
        stmt = (
            select(YoutubeTag.name)
            .join(YoutubeVideoTag, YoutubeTag.tag_pk == YoutubeVideoTag.tag_pk)
            .where(YoutubeVideoTag.video_pk == video_pk)
            .order_by(YoutubeVideoTag.weight.desc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def _get_user(self):
        """youtube_settings.notification.telegram_chat_id에서 User 생성."""
        from app.models.user import User
        from app.services.youtube.settings_manager import get_youtube_settings_manager

        mgr = get_youtube_settings_manager()
        notif_cfg = mgr.get_notification()
        chat_id = (notif_cfg.telegram_chat_id or "").strip()
        if not chat_id:
            return None
        return User(user_id=0, telegram_chat_id=chat_id)


youtube_bot = YoutubeBot()


async def notify_video_callback(video_pk: int) -> None:
    """
    AnalysisPipeline의 notify_callback으로 주입할 함수.
    - 즉시발송(immediate) 모드: 분석 직후 즉시 Telegram 발송.
    - 예약발송(scheduled) 모드: 발송하지 않고 반환 (예약잡이 일괄 처리).
    """
    from app.services.youtube.db_engine import db_engine_manager
    from app.services.youtube.settings_manager import get_youtube_settings_manager

    mgr = get_youtube_settings_manager()
    notif_cfg = mgr.get_notification()

    if not notif_cfg.telegram_enabled:
        return

    if notif_cfg.send_mode == "scheduled":
        print(f"ℹ️  notify_video_callback: 예약발송 모드 — video_pk={video_pk} 발송 보류")
        return

    try:
        engine = await db_engine_manager.get_engine()
    except Exception as e:
        print(f"⚠️  notify_video_callback: DB 연결 실패 — skip (video_pk={video_pk}): {e}")
        return

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    await youtube_bot.notify_standalone(
        session_factory=session_factory,
        video_pk=video_pk,
        low_confidence_threshold=notif_cfg.low_confidence_threshold,
    )
