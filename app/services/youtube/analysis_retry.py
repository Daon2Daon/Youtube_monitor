"""
분석 실패(failed) 영상 자동 재시도 — pending 복구.

- retry_count: 누적 실패 횟수 (실패 시 +1, 성공 시 0)
- max_retries 미만이고, 마지막 실패(updated_at) 후 interval_hours 경과 시 pending 복구
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.youtube_video import YoutubeVideo
from app.services.youtube.settings_manager import PollingSettings

FAILED_RETRY_BATCH_LIMIT = 10


async def reset_failed_videos_for_retry(
    session: AsyncSession,
    polling: PollingSettings,
    *,
    batch_limit: int = FAILED_RETRY_BATCH_LIMIT,
) -> List[int]:
    """
    자동 재시도 대상 failed 영상을 pending으로 되돌린다.

    Returns:
        복구된 video_pk 목록
    """
    if not polling.analysis_retry_enabled:
        return []
    max_retries = int(polling.analysis_max_retries or 0)
    if max_retries < 1:
        return []

    interval_hours = float(polling.analysis_retry_interval_hours or 0)
    if interval_hours <= 0:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=interval_hours)

    select_stmt = (
        select(YoutubeVideo.video_pk)
        .where(YoutubeVideo.analysis_status == "failed")
        .where(YoutubeVideo.retry_count < max_retries)
        .where(YoutubeVideo.updated_at <= cutoff)
        .order_by(YoutubeVideo.updated_at.asc(), YoutubeVideo.video_pk.asc())
        .limit(max(1, batch_limit))
    )
    result = await session.execute(select_stmt)
    pks = [int(r[0]) for r in result.fetchall()]
    if not pks:
        return []

    await session.execute(
        update(YoutubeVideo)
        .where(YoutubeVideo.video_pk.in_(pks))
        .values(
            analysis_status="pending",
            analysis_error=None,
            updated_at=datetime.now(timezone.utc),
        )
    )
    return pks
