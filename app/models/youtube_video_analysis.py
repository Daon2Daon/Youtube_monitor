from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy import JSON
from sqlalchemy.sql import func

from app.models.youtube_base import YoutubeBase


class YoutubeVideoAnalysis(YoutubeBase):
    """video_details + video_summaries를 통합한 영상 분석 결과 테이블 (1:1 with videos)."""

    __tablename__ = "video_analysis"

    video_pk = Column(
        Integer,
        ForeignKey("videos.video_pk", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
        index=True,
    )

    # 요약
    one_line = Column(Text, nullable=False, default="")
    headline = Column(String, nullable=True)
    short_summary_md = Column(Text, nullable=False, default="")
    bullet_points = Column(JSON, nullable=True)

    # 상세 분석
    full_analysis_md = Column(Text, nullable=True)
    full_transcript = Column(Text, nullable=True)
    key_points = Column(JSON, nullable=True)
    insights = Column(JSON, nullable=True)
    entities = Column(JSON, nullable=True)
    sentiment = Column(String, nullable=True)
    confidence_score = Column(Float, nullable=True)

    # 모델/비용 메타
    model_name = Column(String, nullable=True)
    gateway_url = Column(String, nullable=True)
    prompt_version = Column(String, nullable=True)
    token_input = Column(Integer, nullable=True)
    token_output = Column(Integer, nullable=True)
    cost_usd = Column(Float, nullable=True)

    analyzed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
