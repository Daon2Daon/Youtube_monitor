"""
YouTube job_logs 테이블 기록 헬퍼.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import async_sessionmaker

_JOB_TYPE_CHANNEL_POLL = "channel_poll"
_JOB_TYPE_VIDEO_ANALYZE = "video_analyze"
_JOB_TYPE_VIDEO_REANALYZE = "video_reanalyze"
_JOB_TYPE_GATEWAY_HEALTH = "gateway_health"
_JOB_TYPE_NOTIFY = "notify"
JOB_TYPE_NOTIFY = _JOB_TYPE_NOTIFY

_STATUS_SUCCESS = "success"
_STATUS_FAIL = "fail"
_STATUS_SKIP = "skip"


async def write_job_log(
    session_factory: async_sessionmaker,
    job_type: str,
    status: str,
    message: Optional[str] = None,
    duration_ms: Optional[int] = None,
    channel_pk: Optional[int] = None,
    video_pk: Optional[int] = None,
) -> None:
    """job_logs 테이블에 단건 INSERT."""
    from sqlalchemy import text

    try:
        async with session_factory() as sess:
            async with sess.begin():
                await sess.execute(
                    text(
                        """
                        INSERT INTO job_logs
                            (job_type, channel_pk, video_pk, status, message, duration_ms, started_at)
                        VALUES
                            (:job_type, :channel_pk, :video_pk, :status, :message, :duration_ms, :started_at)
                        """
                    ),
                    {
                        "job_type": job_type,
                        "channel_pk": channel_pk,
                        "video_pk": video_pk,
                        "status": status,
                        "message": (message or "")[:500],
                        "duration_ms": duration_ms,
                        "started_at": datetime.now(timezone.utc),
                    },
                )
    except Exception as e:
        print(f"⚠️  job_log 기록 실패 ({job_type}): {e}")


class JobTimer:
    """경과 시간 측정용 컨텍스트 매니저."""

    def __init__(self) -> None:
        self._start: float = 0.0
        self.elapsed_ms: int = 0

    def __enter__(self) -> "JobTimer":
        self._start = time.monotonic()
        return self

    def __exit__(self, *_) -> None:
        self.elapsed_ms = int((time.monotonic() - self._start) * 1000)
