"""
YouTube 모듈 설정 Pydantic 스키마.

민감 필드(password, api_key 등)는 응답 시 마스킹,
업데이트 시 빈 문자열이면 기존 값 유지.
"""

from __future__ import annotations

import re
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class ConnectionTestResponse(BaseModel):
    success: bool
    message: str
    latency_ms: Optional[int] = None


class DBHealthResponse(BaseModel):
    healthy: bool
    message: str
    latency_ms: Optional[int] = None


# ── AI Gateway 설정 ───────────────────────────────────────────────────────────

class AIGatewaySettingsResponse(BaseModel):
    base_url: str
    api_key_masked: str = Field(description="마지막 4자만 노출")
    primary_model: str
    fallback_model: str
    tagging_model: str
    temperature: float
    max_tokens: int
    daily_budget_usd: float


class AIGatewaySettingsUpdate(BaseModel):
    base_url: Optional[str] = None
    api_key: Optional[str] = Field(None, description="빈 문자열이면 기존 값 유지")
    primary_model: Optional[str] = None
    fallback_model: Optional[str] = None
    tagging_model: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=256)
    daily_budget_usd: Optional[float] = Field(None, ge=0.0)


class ModelInfo(BaseModel):
    model_id: str
    provider: Optional[str] = None


class ModelsResponse(BaseModel):
    models: List[ModelInfo]


class AIGatewayTestRequest(BaseModel):
    """
    연결 테스트/분석 테스트 시 저장하지 않고 폼 현재 값을 직접 넘길 때 사용.
    제공된 필드는 DB 저장값보다 우선 적용된다.
    """

    base_url: Optional[str] = None
    api_key: Optional[str] = Field(None, description="빈 문자열이면 DB 저장값 사용")
    primary_model: Optional[str] = None


class GatewayTestAnalyzeResponse(BaseModel):
    success: bool
    message: str
    model_used: Optional[str] = None
    latency_ms: Optional[int] = None


# ── 런타임 설정 (polling + notification 통합) ─────────────────────────────────

class RuntimeSettingsResponse(BaseModel):
    # polling
    master_interval_min: int = Field(description="전체 모니터링 주기(분)")
    pending_analysis_interval_min: int = Field(
        ge=1,
        le=10080,
        description="DB에 pending으로 쌓인 영상을 배치 분석하는 스케줄 잡 주기(분).",
    )
    default_channel_interval_min: int = Field(
        description="채널별 모니터링 주기 기본값(분). 채널 개별 설정이 없을 때 사용"
    )
    youtube_api_key_masked: str
    youtube_daily_quota: int
    window_days: int = Field(description="신규 영상 탐색 윈도우(일)")
    max_concurrent_channels: int
    max_concurrent_analyses: int
    analysis_interval_sec: int = Field(
        description="영상 간 AI 분석 대기 시간(초). 0이면 병렬 처리."
    )
    analysis_retry_enabled: bool = Field(
        description="분석 실패(failed) 영상을 간격·횟수 제한 내에서 자동 pending 복구"
    )
    analysis_max_retries: int = Field(
        ge=0,
        le=20,
        description="자동 재시도 최대 횟수 (retry_count 상한, 미만일 때만 복구)",
    )
    analysis_retry_interval_hours: int = Field(
        ge=1,
        le=168,
        description="재시도 간격(시간). 마지막 실패(updated_at) 후 경과 필요",
    )
    # notification
    telegram_enabled: bool
    wait_between_messages_sec: int
    low_confidence_threshold: float


# ── 프롬프트 설정 ─────────────────────────────────────────────────────────────

class PromptSettingsResponse(BaseModel):
    analysis_prompt: str = Field(description="영상 분석 프롬프트 (Primary·Fallback 공통)")
    prompt_version: str


class PromptSettingsUpdate(BaseModel):
    analysis_prompt: Optional[str] = None


# ── 런타임 설정 업데이트 ────────────────────────────────────────────────────────

class RuntimeSettingsUpdate(BaseModel):
    # polling
    master_interval_min: Optional[int] = Field(
        None, ge=1, le=10080, description="전체 모니터링 주기(분)"
    )
    pending_analysis_interval_min: Optional[int] = Field(None, ge=1, le=10080)
    default_channel_interval_min: Optional[int] = Field(
        None, ge=10, description="채널별 모니터링 주기 기본값(분)"
    )
    youtube_api_key: Optional[str] = Field(None, description="빈 문자열이면 기존 값 유지")
    youtube_daily_quota: Optional[int] = Field(None, ge=100)
    window_days: Optional[int] = Field(None, ge=1, le=3650)
    max_concurrent_channels: Optional[int] = Field(None, ge=1, le=20)
    max_concurrent_analyses: Optional[int] = Field(None, ge=1, le=20)
    analysis_interval_sec: Optional[int] = Field(
        None, ge=0, description="영상 간 AI 분석 대기 시간(초). 0이면 병렬 처리."
    )
    analysis_retry_enabled: Optional[bool] = None
    analysis_max_retries: Optional[int] = Field(None, ge=0, le=20)
    analysis_retry_interval_hours: Optional[int] = Field(None, ge=1, le=168)
    # notification
    telegram_enabled: Optional[bool] = None
    wait_between_messages_sec: Optional[int] = Field(None, ge=0)
    low_confidence_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)


_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


# ── 알림 발송 설정 ─────────────────────────────────────────────────────────────

class NotificationSettingsResponse(BaseModel):
    telegram_enabled: bool
    send_mode: str = Field(description="'immediate' | 'scheduled'")
    scheduled_times: List[str] = Field(description="예약 발송 시각 목록 (HH:MM 24h, 최대 10개)")
    scheduled_max_per_run: int = Field(
        ge=1,
        le=50,
        description="예약발송 스케줄 한 번 실행당 최대 발송 건수.",
    )
    wait_between_messages_sec: int = Field(description="발송 건 간 대기 시간 (초)")
    low_confidence_threshold: float = Field(description="저신뢰도 배지 임계값 (0.0 ~ 1.0)")
    quiet_hours_enabled: bool = Field(
        description="야간(지정 시간) Telegram 발송 제한 활성화 (KST)"
    )
    quiet_hours_start: str = Field(description="제한 시작 시각 HH:MM (KST)")
    quiet_hours_end: str = Field(description="제한 종료 시각 HH:MM (KST, 익일 가능)")


class NotificationSettingsUpdate(BaseModel):
    telegram_enabled: Optional[bool] = None
    send_mode: Optional[str] = Field(None, pattern="^(immediate|scheduled)$")
    scheduled_times: Optional[List[str]] = Field(None, max_length=10)
    scheduled_max_per_run: Optional[int] = Field(None, ge=1, le=50)
    wait_between_messages_sec: Optional[int] = Field(None, ge=0, le=600)
    low_confidence_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    quiet_hours_enabled: Optional[bool] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None

    @field_validator("quiet_hours_start", "quiet_hours_end")
    @classmethod
    def validate_quiet_hours_time(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not _TIME_RE.match(v):
            raise ValueError(f"시각 형식이 올바르지 않습니다 (HH:MM): {v!r}")
        return v

    @field_validator("scheduled_times")
    @classmethod
    def validate_times(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        for t in v:
            if not _TIME_RE.match(t):
                raise ValueError(f"시각 형식이 올바르지 않습니다 (HH:MM): {t!r}")
        return v
