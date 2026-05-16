"""
YouTube 모니터 서비스: 채널 폴링(수집)과 미분석 영상 배치 분석.
SQLite 변환: pg_insert→sqlite_insert, FOR UPDATE SKIP LOCKED→SELECT+UPDATE.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Sequence

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.models.youtube_channel import YoutubeChannel
from app.models.youtube_video import YoutubeVideo
from app.services.youtube.db_engine import db_engine_manager
from app.services.youtube.job_logger import (
    JobTimer,
    _JOB_TYPE_CHANNEL_POLL,
    _JOB_TYPE_GATEWAY_HEALTH,
    _JOB_TYPE_VIDEO_ANALYZE,
    _STATUS_FAIL,
    _STATUS_SKIP,
    _STATUS_SUCCESS,
    write_job_log,
)
from app.services.youtube.settings_manager import PollingSettings, get_youtube_settings_manager
from app.services.youtube.youtube_api import (
    PlaylistItemMeta,
    YouTubeAPIClient,
    YouTubeQuotaExceededError,
    get_youtube_api_client,
)


async def claim_pending_video_pks(session: AsyncSession, limit: int) -> List[int]:
    """
    analysis_status='pending' 행을 선점하고 'processing'으로 변경 후 video_pk 목록 반환.
    SQLite는 FOR UPDATE SKIP LOCKED를 지원하지 않으므로 단순 SELECT+UPDATE로 구현.
    단일 프로세스 환경에서는 동시성 문제가 없습니다.
    """
    if limit < 1:
        return []

    # 처리 대상 선택
    select_stmt = (
        select(YoutubeVideo.video_pk)
        .where(YoutubeVideo.analysis_status == "pending")
        .order_by(YoutubeVideo.published_at.asc(), YoutubeVideo.video_pk.asc())
        .limit(limit)
    )
    result = await session.execute(select_stmt)
    pks = [int(r[0]) for r in result.fetchall()]

    if not pks:
        return []

    # processing으로 상태 변경
    await session.execute(
        update(YoutubeVideo)
        .where(YoutubeVideo.video_pk.in_(pks))
        .values(analysis_status="processing", updated_at=datetime.now(timezone.utc))
    )
    return pks


STALE_PROCESSING_RESET_MINUTES = 180


async def reset_stale_processing_videos(session: AsyncSession, stale_minutes: int) -> int:
    """updated_at이 stale_minutes보다 오래된 processing 행을 pending으로 복구."""
    if stale_minutes < 1:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)
    stmt = (
        update(YoutubeVideo)
        .where(YoutubeVideo.analysis_status == "processing")
        .where(YoutubeVideo.updated_at < cutoff)
        .values(
            analysis_status="pending",
            analysis_error="[자동복구] 분석 중 상태가 비정상적으로 길어져 대기열로 되돌림",
            updated_at=datetime.now(timezone.utc),
        )
    )
    result = await session.execute(stmt)
    return int(result.rowcount or 0)


class MonitorService:
    def __init__(self, polling: PollingSettings):
        self.polling = polling

    async def list_due_channels(self, session: AsyncSession) -> List[YoutubeChannel]:
        """폴링이 필요한 활성 채널 목록 반환."""
        now = datetime.now(timezone.utc)
        stmt = select(YoutubeChannel).where(YoutubeChannel.is_active.is_(True))
        result = await session.execute(stmt)
        channels = result.scalars().all()

        due: List[YoutubeChannel] = []
        for ch in channels:
            if ch.last_checked_at is None:
                due.append(ch)
                continue
            lc = ch.last_checked_at
            if lc.tzinfo is None:
                lc = lc.replace(tzinfo=timezone.utc)
            interval = timedelta(minutes=int(ch.poll_interval_min or self.polling.default_channel_interval_min))
            if now - lc >= interval:
                due.append(ch)
        return due

    async def process_channel(
        self,
        channel: YoutubeChannel,
        session: AsyncSession,
        api_client: YouTubeAPIClient,
        backfill: bool = False,
    ) -> List[int]:
        """채널 폴링 → 신규 영상 INSERT → 새 video_pk 목록 반환."""
        now = datetime.now(timezone.utc)
        window_days = max(1, int(self.polling.window_days or 1))
        cutoff = now - timedelta(days=window_days)

        items: Sequence[PlaylistItemMeta] = await api_client.get_playlist_items_since(
            channel.upload_playlist_id, cutoff
        )
        if not items:
            await self._update_last_checked(session, channel, now)
            return []

        candidate_ids = [it.video_id for it in items]
        new_ids = await self._filter_new_videos(session, candidate_ids)
        if not new_ids:
            await self._update_last_checked(session, channel, now, items[0].video_id)
            return []

        video_metas = await api_client.get_video_details(new_ids)
        if not video_metas:
            await self._update_last_checked(session, channel, now)
            return []

        if not backfill:
            video_metas = [
                v for v in video_metas
                if _parse_iso(v.published_at) >= cutoff
            ]

        if not video_metas:
            await self._update_last_checked(session, channel, now, items[0].video_id)
            return []

        seq_start = await self._next_sequence(session, channel.channel_pk)

        inserted_pks: List[int] = []
        for idx, vm in enumerate(video_metas):
            seq = seq_start + idx
            stmt = (
                sqlite_insert(YoutubeVideo)
                .values(
                    channel_pk=channel.channel_pk,
                    video_id=vm.video_id,
                    video_url=vm.video_url,
                    title=vm.title,
                    description=vm.description,
                    thumbnail_url=vm.thumbnail_url,
                    published_at=_parse_iso(vm.published_at),
                    duration_seconds=_parse_duration(vm.duration),
                    view_count=vm.view_count,
                    like_count=vm.like_count,
                    sequence_in_channel=seq,
                    analysis_status="pending",
                    retry_count=0,
                )
                .on_conflict_do_nothing(index_elements=["video_id"])
            )
            result = await session.execute(stmt)
            # SQLite sqlite_insert + on_conflict_do_nothing은 lastrowid로 pk 확인
            pk = result.lastrowid
            if pk and result.rowcount:
                inserted_pks.append(pk)

        await session.flush()
        await self._update_last_checked(session, channel, now, items[0].video_id)
        return inserted_pks

    async def _filter_new_videos(
        self, session: AsyncSession, video_ids: List[str]
    ) -> List[str]:
        if not video_ids:
            return []
        stmt = select(YoutubeVideo.video_id).where(YoutubeVideo.video_id.in_(video_ids))
        result = await session.execute(stmt)
        existing = {row for row in result.scalars()}
        return [v for v in video_ids if v not in existing]

    async def _next_sequence(self, session: AsyncSession, channel_pk: int) -> int:
        stmt = select(func.max(YoutubeVideo.sequence_in_channel)).where(
            YoutubeVideo.channel_pk == channel_pk
        )
        result = await session.execute(stmt)
        max_seq = result.scalar()
        return 1 if max_seq is None else int(max_seq) + 1

    async def _update_last_checked(
        self,
        session: AsyncSession,
        channel: YoutubeChannel,
        now: datetime,
        last_video_id: Optional[str] = None,
    ) -> None:
        update_vals: dict = {"last_checked_at": now}
        if last_video_id:
            update_vals["last_video_id"] = last_video_id
        await session.execute(
            text(
                "UPDATE channels SET last_checked_at = :ts"
                + (", last_video_id = :vid" if last_video_id else "")
                + " WHERE channel_pk = :pk"
            ),
            {"ts": now, "vid": last_video_id, "pk": channel.channel_pk}
            if last_video_id
            else {"ts": now, "pk": channel.channel_pk},
        )


def _parse_iso(dt_str: str) -> datetime:
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


def _parse_duration(iso_duration: Optional[str]) -> Optional[int]:
    """ISO 8601 duration → 초. 예: PT15M33S → 933."""
    if not iso_duration:
        return None
    try:
        import isodate
        return int(isodate.parse_duration(iso_duration).total_seconds())
    except Exception:
        return None


async def _youtube_master_poll_async() -> None:
    """마스터 폴링 잡의 비동기 구현체."""
    mgr = get_youtube_settings_manager()
    polling_cfg = mgr.get_polling()

    try:
        engine = await db_engine_manager.get_engine()
    except Exception as e:
        print(f"❌ YouTube DB 연결 실패 - 마스터 폴링 SKIP: {e}")
        return

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    service = MonitorService(polling=polling_cfg)

    async with session_factory() as session:
        try:
            due_channels = await service.list_due_channels(session)
        except Exception as e:
            print(f"❌ due_channels 조회 실패: {e}")
            return

    if not due_channels:
        return

    print(f"📡 YouTube 마스터 폴링: {len(due_channels)}개 채널 처리 시작")

    poll_sem = asyncio.Semaphore(int(polling_cfg.max_concurrent_channels or 5))
    api_client = get_youtube_api_client(polling=polling_cfg)

    async def _process_one(channel: YoutubeChannel) -> None:
        async with poll_sem:
            timer = JobTimer()
            with timer:
                try:
                    async with session_factory() as sess:
                        async with sess.begin():
                            new_pks = await service.process_channel(
                                channel=channel,
                                session=sess,
                                api_client=api_client,
                            )

                    await write_job_log(
                        session_factory,
                        job_type=_JOB_TYPE_CHANNEL_POLL,
                        status=_STATUS_SUCCESS,
                        message=f"신규 영상 {len(new_pks)}건 수집" if new_pks else "신규 영상 없음",
                        duration_ms=timer.elapsed_ms,
                        channel_pk=channel.channel_pk,
                    )

                except YouTubeQuotaExceededError as e:
                    print(f"⚠️  YouTube 쿼터 초과: {e}")
                    await write_job_log(
                        session_factory,
                        job_type=_JOB_TYPE_CHANNEL_POLL,
                        status=_STATUS_SKIP,
                        message=f"쿼터 초과: {e}",
                        duration_ms=timer.elapsed_ms,
                        channel_pk=channel.channel_pk,
                    )
                except Exception as e:
                    print(f"❌ 채널 처리 실패 (channel_pk={channel.channel_pk}): {e}")
                    await write_job_log(
                        session_factory,
                        job_type=_JOB_TYPE_CHANNEL_POLL,
                        status=_STATUS_FAIL,
                        message=str(e)[:500],
                        duration_ms=timer.elapsed_ms,
                        channel_pk=channel.channel_pk,
                    )

    try:
        await asyncio.gather(*[_process_one(ch) for ch in due_channels], return_exceptions=True)
    finally:
        await api_client.aclose()

    print("✅ YouTube 마스터 폴링 완료")


async def _youtube_pending_analysis_async() -> None:
    """스케줄 잡: DB에서 pending 영상 1건만 선점한 뒤 AI 분석·DB 저장."""
    mgr = get_youtube_settings_manager()
    polling_cfg = mgr.get_polling()

    try:
        engine = await db_engine_manager.get_engine()
    except Exception as e:
        print(f"❌ YouTube DB 연결 실패 - 미분석 영상 분석 잡 SKIP: {e}")
        return

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    batch_limit = 1

    n_reset = 0
    claimed: List[int] = []
    async with session_factory() as sess:
        async with sess.begin():
            n_reset = await reset_stale_processing_videos(sess, STALE_PROCESSING_RESET_MINUTES)
            claimed = await claim_pending_video_pks(sess, batch_limit)

    if n_reset:
        print(f"♻️  YouTube: 오래된 분석중(processing) 영상 {n_reset}건을 pending으로 복구")

    if not claimed:
        return

    print("🧠 YouTube 미분석 배치: 1건 분석 시작")
    analysis_sem = asyncio.Semaphore(1)
    await _analyze_batch(claimed, analysis_sem, polling_cfg, engine=engine)
    print("✅ YouTube 미분석 배치 완료")


def youtube_pending_analysis_sync() -> None:
    asyncio.run(_youtube_pending_analysis_async())


async def _analyze_batch(
    video_pks: List[int],
    sem: asyncio.Semaphore,
    polling_cfg: PollingSettings,
    *,
    engine: AsyncEngine | None = None,
) -> None:
    from app.services.youtube.analyzer import build_analysis_pipeline
    from app.services.youtube.youtube_bot import notify_video_callback

    eng = engine if engine is not None else await db_engine_manager.get_engine()
    session_factory = async_sessionmaker(eng, expire_on_commit=False)

    pipeline = build_analysis_pipeline(notify_callback=notify_video_callback)
    interval_sec = int(polling_cfg.analysis_interval_sec or 0)

    async def _analyze_one(video_pk: int) -> None:
        async with sem:
            timer = JobTimer()
            channel_pk: Optional[int] = None
            video_title: Optional[str] = None
            with timer:
                try:
                    async with session_factory() as sess:
                        async with sess.begin():
                            stmt = select(YoutubeVideo).where(YoutubeVideo.video_pk == video_pk)
                            result = await sess.execute(stmt)
                            video = result.scalar_one_or_none()
                            if not video:
                                return
                            video_title = video.title

                            ch_stmt = select(YoutubeChannel).where(
                                YoutubeChannel.channel_pk == video.channel_pk
                            )
                            ch_result = await sess.execute(ch_stmt)
                            channel = ch_result.scalar_one_or_none()
                            channel_pk = video.channel_pk

                            await pipeline.run_and_save(
                                session=sess,
                                video_pk=video_pk,
                                video_url=video.video_url,
                                channel_name=channel.channel_name if channel else "",
                                published_at_str=video.published_at.isoformat(),
                            )
                    from app.services.youtube.youtube_bot import notify_video_callback

                    await notify_video_callback(video_pk)
                except Exception as e:
                    print(f"❌ 분석 실패 (video_pk={video_pk}): {e}")
                    try:
                        async with session_factory() as fail_sess:
                            async with fail_sess.begin():
                                await fail_sess.execute(
                                    update(YoutubeVideo)
                                    .where(YoutubeVideo.video_pk == video_pk)
                                    .values(
                                        analysis_status="failed",
                                        analysis_error=str(e)[:500],
                                        updated_at=datetime.now(timezone.utc),
                                    )
                                )
                    except Exception as upd_exc:
                        print(f"⚠️  분석 실패 상태 DB 기록 오류 (video_pk={video_pk}): {upd_exc}")
                    await write_job_log(
                        session_factory,
                        job_type=_JOB_TYPE_VIDEO_ANALYZE,
                        status=_STATUS_FAIL,
                        message=str(e)[:500],
                        duration_ms=timer.elapsed_ms,
                        channel_pk=channel_pk,
                        video_pk=video_pk,
                    )
                else:
                    await write_job_log(
                        session_factory,
                        job_type=_JOB_TYPE_VIDEO_ANALYZE,
                        status=_STATUS_SUCCESS,
                        message=f"분석 완료 - {video_title}" if video_title else "분석 완료",
                        duration_ms=timer.elapsed_ms,
                        channel_pk=channel_pk,
                        video_pk=video_pk,
                    )

    if interval_sec > 0:
        for idx, pk in enumerate(video_pks):
            if idx > 0:
                print(f"⏳ 분석 간격 대기 {interval_sec}초 (video_pk={pk})")
                await asyncio.sleep(interval_sec)
            await _analyze_one(pk)
    else:
        await asyncio.gather(*[_analyze_one(pk) for pk in video_pks], return_exceptions=True)


def youtube_master_poll_sync() -> None:
    asyncio.run(_youtube_master_poll_async())


async def _youtube_gateway_health_async() -> None:
    """litellm Gateway 헬스체크 (30분 주기, 실패 시에만 로그 기록)."""
    try:
        engine = await db_engine_manager.get_engine()
    except Exception:
        engine = None

    session_factory = async_sessionmaker(engine, expire_on_commit=False) if engine else None
    timer = JobTimer()

    with timer:
        client = None
        try:
            from app.services.youtube.llm_client import get_litellm_client

            mgr = get_youtube_settings_manager()
            ai_cfg = mgr.get_ai_gateway()
            if not ai_cfg.base_url or not ai_cfg.api_key:
                return
            client = get_litellm_client(settings=ai_cfg)
            await client.get_models(force_refresh=True)
            # 정상 시에는 로그 미기록
        except Exception as e:
            print(f"❌ YouTube Gateway 헬스체크 실패: {e}")
            if session_factory:
                await write_job_log(
                    session_factory,
                    job_type=_JOB_TYPE_GATEWAY_HEALTH,
                    status=_STATUS_FAIL,
                    message=str(e)[:500],
                    duration_ms=timer.elapsed_ms,
                )
        finally:
            if client:
                try:
                    await client.aclose()
                except Exception:
                    pass


def youtube_gateway_health_sync() -> None:
    asyncio.run(_youtube_gateway_health_async())
