from sqlalchemy import BigInteger, Boolean, Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func

from app.models.youtube_base import YoutubeBase


class YoutubeChannel(YoutubeBase):
    __tablename__ = "channels"

    channel_pk = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(String, nullable=False, unique=True)
    channel_name = Column(String, nullable=False)
    channel_handle = Column(String, nullable=True)
    upload_playlist_id = Column(String, nullable=False)
    thumbnail_url = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    category = Column(String, nullable=True)
    poll_interval_min = Column(Integer, nullable=False, default=720)
    is_active = Column(Boolean, nullable=False, default=True)
    notify_enabled = Column(Boolean, nullable=False, default=True)
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    last_video_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
