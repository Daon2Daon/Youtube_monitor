"""
야간(지정 시간대) Telegram 알림 발송 제한.

기본 타임존: Asia/Seoul (KST).
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

DEFAULT_TZ = ZoneInfo("Asia/Seoul")


def _minutes_from_hhmm(hhmm: str) -> int:
    parts = (hhmm or "").strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"HH:MM 형식이 아님: {hhmm!r}")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"시각 범위 오류: {hhmm!r}")
    return hour * 60 + minute


def is_in_quiet_hours(
    start_hhmm: str,
    end_hhmm: str,
    *,
    now: datetime | None = None,
    tz: ZoneInfo | None = None,
) -> bool:
    """
    현재 시각이 [start, end) 제한 구간에 포함되는지 판단.

    - start < end: 같은 날 구간 (예: 09:00~17:00)
    - start > end: 자정을 넘는 구간 (예: 22:00~07:00)
    - start == end: 하루 종일 제한으로 간주
    """
    zone = tz or DEFAULT_TZ
    local = (now or datetime.now(zone)).astimezone(zone)
    cur = local.hour * 60 + local.minute
    start = _minutes_from_hhmm(start_hhmm)
    end = _minutes_from_hhmm(end_hhmm)

    if start == end:
        return True
    if start < end:
        return start <= cur < end
    return cur >= start or cur < end


def is_quiet_hours_now(
    enabled: bool,
    start_hhmm: str,
    end_hhmm: str,
    *,
    now: datetime | None = None,
    tz: ZoneInfo | None = None,
) -> bool:
    if not enabled:
        return False
    try:
        return is_in_quiet_hours(start_hhmm, end_hhmm, now=now, tz=tz)
    except ValueError:
        return False


def quiet_hours_label(start_hhmm: str, end_hhmm: str) -> str:
    return f"{start_hhmm}~{end_hhmm} (KST)"


CATCHUP_CRON_OFFSET_MINUTES = 5


def parse_hhmm(hhmm: str) -> tuple[int, int]:
    """HH:MM → (hour, minute)."""
    total = _minutes_from_hhmm(hhmm)
    return total // 60, total % 60


def catchup_cron_time(
    end_hhmm: str,
    offset_minutes: int = CATCHUP_CRON_OFFSET_MINUTES,
) -> tuple[int, int] | None:
    """
    야간 제한 종료 시각 + offset 분의 Cron (hour, minute).
    형식 오류 시 None.
    """
    try:
        end_total = _minutes_from_hhmm(end_hhmm)
    except ValueError:
        return None
    run_total = (end_total + offset_minutes) % (24 * 60)
    return run_total // 60, run_total % 60


def is_all_day_quiet_hours(start_hhmm: str, end_hhmm: str) -> bool:
    """start == end 이면 종일 제한."""
    try:
        return _minutes_from_hhmm(start_hhmm) == _minutes_from_hhmm(end_hhmm)
    except ValueError:
        return False
