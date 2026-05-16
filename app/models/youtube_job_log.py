from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.models.youtube_base import YoutubeBase


class YoutubeJobLog(YoutubeBase):
    __tablename__ = "job_logs"

    log_pk = Column(Integer, primary_key=True, autoincrement=True)
    job_type = Column(String, nullable=False)
    channel_pk = Column(Integer, nullable=True)
    video_pk = Column(Integer, nullable=True)
    status = Column(String, nullable=False)
    message = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
