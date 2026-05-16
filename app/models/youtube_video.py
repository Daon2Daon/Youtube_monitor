from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from app.models.youtube_base import YoutubeBase


class YoutubeVideo(YoutubeBase):
    __tablename__ = "videos"

    video_pk = Column(Integer, primary_key=True, autoincrement=True)
    channel_pk = Column(
        Integer,
        ForeignKey("channels.channel_pk", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    video_id = Column(String, nullable=False, unique=True)
    video_url = Column(String, nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    thumbnail_url = Column(String, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=False, index=True)
    duration_seconds = Column(Integer, nullable=True)
    view_count = Column(Integer, nullable=True)
    like_count = Column(Integer, nullable=True)
    sequence_in_channel = Column(Integer, nullable=True)
    analysis_status = Column(String, nullable=False, default="pending")
    analysis_error = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    notified_at = Column(DateTime(timezone=True), nullable=True)
    source_channel_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
