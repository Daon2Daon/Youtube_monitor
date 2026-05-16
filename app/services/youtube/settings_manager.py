"""
YouTube 모듈 런타임 설정 로더 (SQLite youtube_settings)
Fernet으로 is_secret 필드 복호화, 카테고리별 60초 TTL 메모리 캐시.
"""

from __future__ import annotations

import json
import time
import json as _json
from dataclasses import dataclass, field, replace
from typing import Any, Callable, List, Optional

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.models.youtube_setting import YoutubeSetting


class YoutubeSettingsSecretError(RuntimeError):
    """비밀 필드 복호화에 실패했거나 Fernet 키가 없을 때."""


def _fernet_from_key(key: str | None) -> Fernet | None:
    if not (key and key.strip()):
        return None
    try:
        return Fernet(key.strip().encode("utf-8"))
    except Exception as e:
        raise YoutubeSettingsSecretError(f"YOUTUBE_SETTINGS_FERNET_KEY가 유효하지 않습니다: {e}") from e


def mask_secret(plain: str, keep_last: int = 4) -> str:
    if not plain:
        return ""
    if len(plain) <= keep_last:
        return plain
    return "*" * (len(plain) - keep_last) + plain[-keep_last:]


def _raw_row_value(row: YoutubeSetting, fernet: Fernet | None) -> str:
    if int(row.is_secret or 0):
        blob = row.value_enc
        if not blob:
            return ""
        if fernet is None:
            raise YoutubeSettingsSecretError(
                "비밀 설정을 읽으려면 YOUTUBE_SETTINGS_FERNET_KEY가 필요합니다."
            )
        try:
            return fernet.decrypt(blob).decode("utf-8")
        except InvalidToken as e:
            raise YoutubeSettingsSecretError("암호화된 설정 복호화에 실패했습니다.") from e
    return row.value if row.value is not None else ""


def _coerce_value(raw: str, value_type: str | None) -> Any:
    vt = (value_type or "string").lower()
    if vt == "string":
        return raw
    if vt == "int":
        return int(raw) if raw not in ("", None) else 0
    if vt == "float":
        return float(raw) if raw not in ("", None) else 0.0
    if vt == "bool":
        return str(raw).lower() in ("1", "true", "yes", "on")
    if vt == "json":
        return json.loads(raw) if raw else None
    return raw


def _row_typed(row: YoutubeSetting | None, fernet: Fernet | None) -> Any:
    if row is None:
        return None
    raw = _raw_row_value(row, fernet)
    return _coerce_value(raw, row.value_type)


def _resolve_window_days(by_key: dict, fernet: Fernet | None) -> int:
    """신규 영상 탐색 윈도우(일). window_days 우선, 없으면 legacy window_hours 변환."""
    raw_days = _row_typed(by_key.get("window_days"), fernet)
    if raw_days not in (None, ""):
        return max(1, int(raw_days))
    raw_hours = _row_typed(by_key.get("window_hours"), fernet)
    if raw_hours not in (None, ""):
        hours = int(raw_hours)
        return max(1, (hours + 23) // 24)
    return 1


@dataclass
class AIGatewaySettings:
    base_url: str = "http://litellm:4000"
    api_key: str = ""
    primary_model: str = "gemini/gemini-2.5-flash"
    fallback_model: str = "gemini/gemini-2.5-flash"
    tagging_model: str = "gemini/gemini-2.5-flash"
    temperature: float = 0.3
    max_tokens: int = 8192
    daily_budget_usd: float = 2.0

    @classmethod
    def from_rows(cls, rows: list[YoutubeSetting], fernet: Fernet | None) -> AIGatewaySettings:
        by_key = {r.key: r for r in rows}
        return cls(
            base_url=str(_row_typed(by_key.get("base_url"), fernet) or "http://litellm:4000"),
            api_key=str(_row_typed(by_key.get("api_key"), fernet) or ""),
            primary_model=str(
                _row_typed(by_key.get("primary_model"), fernet) or "gemini/gemini-2.5-flash"
            ),
            fallback_model=str(
                _row_typed(by_key.get("fallback_model"), fernet) or "gemini/gemini-2.5-flash"
            ),
            tagging_model=str(
                _row_typed(by_key.get("tagging_model"), fernet) or "gemini/gemini-2.5-flash"
            ),
            temperature=float(_row_typed(by_key.get("temperature"), fernet) or 0.3),
            max_tokens=int(_row_typed(by_key.get("max_tokens"), fernet) or 8192),
            daily_budget_usd=float(_row_typed(by_key.get("daily_budget_usd"), fernet) or 2.0),
        )


@dataclass
class PromptSettings:
    analysis_prompt: str = ""

    @classmethod
    def from_rows(cls, rows: list[YoutubeSetting], fernet: Fernet | None) -> "PromptSettings":
        by_key = {r.key: r for r in rows}
        primary = str(_row_typed(by_key.get("primary_prompt"), fernet) or "")
        legacy_fallback = str(_row_typed(by_key.get("fallback_prompt"), fernet) or "")
        analysis = str(_row_typed(by_key.get("analysis_prompt"), fernet) or "")
        return cls(analysis_prompt=analysis or primary or legacy_fallback)


@dataclass
class PollingSettings:
    master_interval_min: int = 12
    pending_analysis_interval_min: int = 12
    default_channel_interval_min: int = 720
    youtube_api_key: str = ""
    youtube_daily_quota: int = 10000
    window_days: int = 1
    max_concurrent_channels: int = 5
    max_concurrent_analyses: int = 3
    analysis_interval_sec: int = 120

    @classmethod
    def from_rows(cls, rows: list[YoutubeSetting], fernet: Fernet | None) -> PollingSettings:
        by_key = {r.key: r for r in rows}
        master_interval_min = int(_row_typed(by_key.get("master_interval_min"), fernet) or 12)
        raw_pending = _row_typed(by_key.get("pending_analysis_interval_min"), fernet)
        if raw_pending in (None, ""):
            pending_analysis_interval_min = master_interval_min
        else:
            pending_analysis_interval_min = int(raw_pending)
            if pending_analysis_interval_min < 1:
                pending_analysis_interval_min = master_interval_min
            elif pending_analysis_interval_min > 10080:
                pending_analysis_interval_min = 10080
        return cls(
            master_interval_min=master_interval_min,
            pending_analysis_interval_min=pending_analysis_interval_min,
            default_channel_interval_min=int(
                _row_typed(by_key.get("default_channel_interval_min"), fernet) or 720
            ),
            youtube_api_key=str(_row_typed(by_key.get("youtube_api_key"), fernet) or ""),
            youtube_daily_quota=int(_row_typed(by_key.get("youtube_daily_quota"), fernet) or 10000),
            window_days=_resolve_window_days(by_key, fernet),
            max_concurrent_channels=int(
                _row_typed(by_key.get("max_concurrent_channels"), fernet) or 5
            ),
            max_concurrent_analyses=int(
                _row_typed(by_key.get("max_concurrent_analyses"), fernet) or 3
            ),
            analysis_interval_sec=int(
                _row_typed(by_key.get("analysis_interval_sec"), fernet) or 120
            ),
        )


@dataclass
class NotificationSettings:
    telegram_enabled: bool = True
    send_mode: str = "immediate"
    scheduled_times: List[str] = field(default_factory=list)
    scheduled_max_per_run: int = 5
    wait_between_messages_sec: int = 30
    low_confidence_threshold: float = 0.5
    telegram_chat_id: str = ""

    @classmethod
    def from_rows(cls, rows: list[YoutubeSetting], fernet: Fernet | None) -> NotificationSettings:
        by_key = {r.key: r for r in rows}
        te_row = by_key.get("telegram_enabled")
        if te_row is None:
            telegram_enabled = True
        else:
            telegram_enabled = bool(_row_typed(te_row, fernet))

        raw_times = _row_typed(by_key.get("scheduled_times"), fernet)
        if isinstance(raw_times, list):
            scheduled_times = [str(t) for t in raw_times]
        elif isinstance(raw_times, str):
            try:
                parsed = _json.loads(raw_times)
                scheduled_times = [str(t) for t in parsed] if isinstance(parsed, list) else []
            except Exception:
                scheduled_times = []
        else:
            scheduled_times = []

        raw_cap = _row_typed(by_key.get("scheduled_max_per_run"), fernet)
        if raw_cap in (None, ""):
            scheduled_max_per_run = 5
        else:
            scheduled_max_per_run = max(1, min(50, int(raw_cap)))

        return cls(
            telegram_enabled=telegram_enabled,
            send_mode=str(_row_typed(by_key.get("send_mode"), fernet) or "immediate"),
            scheduled_times=scheduled_times,
            scheduled_max_per_run=scheduled_max_per_run,
            wait_between_messages_sec=int(
                _row_typed(by_key.get("wait_between_messages_sec"), fernet) or 30
            ),
            low_confidence_threshold=float(
                _row_typed(by_key.get("low_confidence_threshold"), fernet) or 0.5
            ),
            telegram_chat_id=str(_row_typed(by_key.get("telegram_chat_id"), fernet) or ""),
        )


class SettingsManager:
    """카테고리별 설정 조회 + TTL 캐시."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        fernet_key: str | None = None,
        cache_ttl_sec: float = 60.0,
    ):
        self._session_factory = session_factory
        self._cache_ttl = cache_ttl_sec
        self._cache: dict[str, tuple[Any, float]] = {}
        resolved_key = (
            app_settings.YOUTUBE_SETTINGS_FERNET_KEY if fernet_key is None else fernet_key
        )
        self._fernet = _fernet_from_key(resolved_key)

    def invalidate(self, category: str | None = None) -> None:
        if category is None:
            self._cache.clear()
        else:
            self._cache.pop(category, None)

    def _get_cached(self, category: str, loader: Callable[[], Any]) -> Any:
        now = time.monotonic()
        hit = self._cache.get(category)
        if hit is not None:
            val, exp = hit
            if now < exp:
                return val
        val = loader()
        self._cache[category] = (val, now + self._cache_ttl)
        return val

    def _fetch_category(self, category: str) -> list[YoutubeSetting]:
        db = self._session_factory()
        try:
            return db.query(YoutubeSetting).filter(YoutubeSetting.category == category).all()
        finally:
            db.close()

    def get_ai_gateway(self) -> AIGatewaySettings:
        def load() -> AIGatewaySettings:
            rows = self._fetch_category("ai_gateway")
            cfg = AIGatewaySettings.from_rows(rows, self._fernet)
            env_key = (app_settings.YOUTUBE_BOOTSTRAP_LITELLM_API_KEY or "").strip()
            if env_key and not (cfg.api_key or "").strip():
                cfg = replace(cfg, api_key=env_key)
            return cfg
        return self._get_cached("ai_gateway", load)

    def get_polling(self) -> PollingSettings:
        def load() -> PollingSettings:
            rows = self._fetch_category("polling")
            return PollingSettings.from_rows(rows, self._fernet)
        return self._get_cached("polling", load)

    def get_prompts(self) -> PromptSettings:
        def load() -> PromptSettings:
            rows = self._fetch_category("prompts")
            return PromptSettings.from_rows(rows, self._fernet)
        return self._get_cached("prompts", load)

    def get_notification(self) -> NotificationSettings:
        def load() -> NotificationSettings:
            rows = self._fetch_category("notification")
            return NotificationSettings.from_rows(rows, self._fernet)
        return self._get_cached("notification", load)


_manager_singleton: SettingsManager | None = None


def get_youtube_settings_manager() -> SettingsManager:
    """앱 기본 SessionLocal + config Fernet 키로 매니저 반환 (싱글톤)."""
    global _manager_singleton
    if _manager_singleton is None:
        from app.database import SessionLocal

        _manager_singleton = SettingsManager(
            session_factory=SessionLocal, fernet_key=None, cache_ttl_sec=60.0
        )
    return _manager_singleton
