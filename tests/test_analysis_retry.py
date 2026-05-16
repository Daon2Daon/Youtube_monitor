"""analysis_retry 자동 복구 단위 테스트."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.youtube.analysis_retry import reset_failed_videos_for_retry
from app.services.youtube.settings_manager import PollingSettings

KST = timezone.utc


def _polling(**kwargs) -> PollingSettings:
    base = PollingSettings()
    for k, v in kwargs.items():
        setattr(base, k, v)
    return base


@pytest.mark.asyncio
async def test_reset_failed_disabled():
    session = AsyncMock()
    pks = await reset_failed_videos_for_retry(
        session, _polling(analysis_retry_enabled=False)
    )
    assert pks == []
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_reset_failed_returns_pks():
    session = AsyncMock()
    select_result = MagicMock()
    select_result.fetchall.return_value = [(10,), (20,)]
    update_result = MagicMock()
    update_result.rowcount = 2
    session.execute = AsyncMock(side_effect=[select_result, update_result])

    pks = await reset_failed_videos_for_retry(
        session,
        _polling(
            analysis_retry_enabled=True,
            analysis_max_retries=3,
            analysis_retry_interval_hours=6,
        ),
        batch_limit=10,
    )
    assert pks == [10, 20]
    assert session.execute.await_count == 2
