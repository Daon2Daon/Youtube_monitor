"""quiet_hours 유틸 단위 테스트."""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.youtube.quiet_hours import (
    catchup_cron_time,
    is_all_day_quiet_hours,
    is_in_quiet_hours,
    is_quiet_hours_now,
)

KST = ZoneInfo("Asia/Seoul")


def _dt(h: int, m: int = 0) -> datetime:
    return datetime(2026, 5, 16, h, m, tzinfo=KST)


def test_overnight_quiet():
    assert is_in_quiet_hours("22:00", "07:00", now=_dt(23, 0))
    assert is_in_quiet_hours("22:00", "07:00", now=_dt(6, 30))
    assert not is_in_quiet_hours("22:00", "07:00", now=_dt(12, 0))


def test_same_day_quiet():
    assert is_in_quiet_hours("09:00", "18:00", now=_dt(10, 0))
    assert not is_in_quiet_hours("09:00", "18:00", now=_dt(20, 0))


def test_disabled():
    assert not is_quiet_hours_now(False, "22:00", "07:00", now=_dt(23, 0))


def test_catchup_cron_time():
    assert catchup_cron_time("07:00") == (7, 5)
    assert catchup_cron_time("23:58") == (0, 3)


def test_all_day_quiet():
    assert is_all_day_quiet_hours("22:00", "22:00")
    assert not is_all_day_quiet_hours("22:00", "07:00")
