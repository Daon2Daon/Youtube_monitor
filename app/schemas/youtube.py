"""
YouTube 모듈 Pydantic 스키마 (채널 / 영상 / 태그 / 잡 / 통계).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── 채널 ─────────────────────────────────────────────────────────────────────

class ChannelCreate(BaseModel):
    """채널 추가 요청."""
    channel_input: str = Field(
        ...,
        description="YouTube 채널 ID / @핸들 / 채널 URL 중 하나",
        examples=["@JTBC_News", "UCxxxxxxxxxxxxxxxxxxxxxxxx"],
    )
    category: Optional[str] = None
    poll_interval_min: int = Field(720, ge=10, description="모니터링 주기 (분), 최소 10분")
    notify_enabled: bool = True
    auto_poll_now: bool = Field(False, description="추가 즉시 모니터링 트리거 여부")
    initial_window_days: int = Field(1, ge=1, le=3650, description="초기 폴링 시 탐색할 과거 일수")


class ChannelUpdate(BaseModel):
    """채널 부분 수정 요청."""
    is_active: Optional[bool] = None
    notify_enabled: Optional[bool] = None
    poll_interval_min: Optional[int] = Field(None, ge=10)
    category: Optional[str] = None


class ChannelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    channel_pk: int
    channel_id: str
    channel_name: str
    channel_handle: Optional[str] = None
    thumbnail_url: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    poll_interval_min: int
    is_active: bool
    notify_enabled: bool
    last_checked_at: Optional[datetime] = None
    last_video_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ── 영상 ─────────────────────────────────────────────────────────────────────

class VideoSummaryEmbed(BaseModel):
    """영상 목록에 인라인으로 포함되는 요약 (경량)."""
    model_config = ConfigDict(from_attributes=True)

    one_line: str
    headline: Optional[str] = None


class VideoResponse(BaseModel):
    """영상 목록 아이템."""
    model_config = ConfigDict(from_attributes=True)

    video_pk: int
    channel_pk: int
    video_id: str
    video_url: str
    title: str
    thumbnail_url: Optional[str] = None
    published_at: datetime
    duration_seconds: Optional[int] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    analysis_status: str
    notified_at: Optional[datetime] = None
    created_at: datetime
    summary: Optional[VideoSummaryEmbed] = None
    source_channel_name: Optional[str] = None


class VideoDetailResponse(BaseModel):
    """영상 상세 (video_analysis + tags 포함)."""
    model_config = ConfigDict(from_attributes=True)

    video_pk: int
    channel_pk: int
    video_id: str
    video_url: str
    title: str
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    published_at: datetime
    duration_seconds: Optional[int] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    sequence_in_channel: Optional[int] = None
    analysis_status: str
    analysis_error: Optional[str] = None
    retry_count: int
    notified_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    # 분석 결과
    one_line: Optional[str] = None
    headline: Optional[str] = None
    short_summary_md: Optional[str] = None
    full_analysis_md: Optional[str] = None
    bullet_points: Optional[List[str]] = None
    key_points: Optional[List[Any]] = None
    insights: Optional[List[Any]] = None
    entities: Optional[List[Any]] = None
    sentiment: Optional[str] = None
    confidence_score: Optional[float] = None
    model_name: Optional[str] = None
    analyzed_at: Optional[datetime] = None

    # 태그
    tags: List[str] = Field(default_factory=list)
    source_channel_name: Optional[str] = None


# ── 페이지네이션 래퍼 ──────────────────────────────────────────────────────────

class PaginatedVideos(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[VideoResponse]


# ── 태그 ─────────────────────────────────────────────────────────────────────

class TagResponse(BaseModel):
    """태그 클라우드 아이템."""
    model_config = ConfigDict(from_attributes=True)

    tag_pk: int
    name: str
    tag_type: str
    video_count: int = 0


# ── 잡 로그 ──────────────────────────────────────────────────────────────────

class JobLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    log_pk: int
    job_type: str
    channel_pk: Optional[int] = None
    video_pk: Optional[int] = None
    status: str
    message: Optional[str] = None
    duration_ms: Optional[int] = None
    started_at: datetime


class PaginatedJobLogs(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[JobLogResponse]


# ── 통계 ─────────────────────────────────────────────────────────────────────

class StatsResponse(BaseModel):
    total_channels: int
    active_channels: int
    total_videos: int
    analyzed_videos: int
    pending_videos: int
    failed_videos: int
    notified_videos: int
    total_tags: int
    last_poll_at: Optional[datetime] = None


# ── 즉시 모니터링 트리거 응답 ──────────────────────────────────────────────────

class PollTriggerResponse(BaseModel):
    job_id: str
    message: str


class VideoNotifyRequest(BaseModel):
    """영상 상세에서 수동 Telegram 발송."""
    force: bool = Field(
        False,
        description="true이면 이미 발송된 영상(notified_at 있음)도 다시 발송",
    )


class VideoNotifyResponse(BaseModel):
    success: bool
    message: str
    notified_at: Optional[datetime] = None


# ── 즉시(추가 영상) 분석 ────────────────────────────────────────────────────────

class InstantAnalyzeRequest(BaseModel):
    """YouTube URL을 입력받아 즉시 분석 시작."""
    video_url: str = Field(..., description="분석할 YouTube 영상 URL")
    custom_prompt: Optional[str] = Field(None, description="이 영상 전용 프롬프트 (선택)")


class InstantAnalyzeResponse(BaseModel):
    """즉시 분석 트리거 응답."""
    video_pk: int
    video_id: str
    title: str
    source_channel_name: str
    analysis_status: str
    existing: bool = Field(description="True = 이미 DB에 있던 영상, False = 신규 등록 후 분석 시작")
    message: str
