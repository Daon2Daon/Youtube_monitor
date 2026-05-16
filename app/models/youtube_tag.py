from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.sql import func

from app.models.youtube_base import YoutubeBase


class YoutubeTag(YoutubeBase):
    __tablename__ = "tags"

    tag_pk = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    tag_type = Column(String, nullable=False, default="topic")
    video_count = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
