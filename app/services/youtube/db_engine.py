"""
YouTube Monitor 독립 앱: SQLite 비동기 엔진 관리.

PostgreSQL asyncpg 대신 aiosqlite를 사용합니다.
단일 SQLite 파일 (DATABASE_URL) 기반으로 동작하므로,
PG처럼 DB 설정 여부를 체크할 필요 없이 항상 엔진을 반환합니다.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import settings


@dataclass
class EngineHealth:
    ok: bool
    message: Optional[str] = None
    latency_ms: Optional[float] = None


class DBNotConfiguredError(RuntimeError):
    """SQLite는 항상 사용 가능하므로 실질적으로 발생하지 않지만,
    기존 코드와의 호환을 위해 유지합니다."""


class _DBEngineManager:
    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None

    def _get_async_url(self) -> str:
        url = settings.DATABASE_URL
        # sqlite:///path → sqlite+aiosqlite:///path
        if url.startswith("sqlite:///"):
            return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
        if url.startswith("sqlite+aiosqlite"):
            return url
        raise DBNotConfiguredError(f"지원하지 않는 DATABASE_URL 형식: {url}")

    async def get_engine(self) -> AsyncEngine:
        if self._engine is not None:
            return self._engine

        async_url = self._get_async_url()
        self._engine = create_async_engine(
            async_url,
            connect_args={"check_same_thread": False},
            echo=False,
        )
        # SQLite WAL 모드 활성화 (단일 프로세스 내 동시 읽기/쓰기 성능 향상)
        from sqlalchemy import event, text

        @event.listens_for(self._engine.sync_engine, "connect")
        def set_wal_mode(dbapi_conn, _connection_record):
            dbapi_conn.execute("PRAGMA journal_mode=WAL")
            dbapi_conn.execute("PRAGMA synchronous=NORMAL")

        return self._engine

    async def dispose(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None

    async def test_connection_only(self) -> EngineHealth:
        """SQLite 연결 테스트 (SELECT 1)."""
        from sqlalchemy import text

        try:
            engine = await self.get_engine()
            t0 = time.monotonic()
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return EngineHealth(ok=True, latency_ms=(time.monotonic() - t0) * 1000)
        except Exception as exc:
            return EngineHealth(ok=False, message=str(exc))

    async def apply_schema(self) -> None:
        """YoutubeBase 스키마 강제 적용 (ensure_schema 위임)."""
        await self.ensure_schema()

    async def health_check(self) -> EngineHealth:
        """연결 상태 확인 (test_connection_only 위임)."""
        return await self.test_connection_only()

    async def ensure_schema(self) -> None:
        """YoutubeBase 메타데이터로 테이블 생성 (없을 때만)."""
        from app.models.youtube_base import YoutubeBase
        from app.models import (  # noqa: F401
            youtube_channel,
            youtube_video,
            youtube_video_analysis,
            youtube_tag,
            youtube_video_tag,
            youtube_job_log,
        )

        engine = await self.get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(YoutubeBase.metadata.create_all)
        print("✅ YouTube 데이터 테이블 생성/확인 완료")


db_engine_manager = _DBEngineManager()
