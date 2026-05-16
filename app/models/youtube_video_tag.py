from sqlalchemy import Column, Float, ForeignKey, Integer

from app.models.youtube_base import YoutubeBase


class YoutubeVideoTag(YoutubeBase):
    __tablename__ = "video_tags"

    video_pk = Column(
        Integer,
        ForeignKey("videos.video_pk", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_pk = Column(
        Integer,
        ForeignKey("tags.tag_pk", ondelete="CASCADE"),
        primary_key=True,
    )
    weight = Column(Float, nullable=True, default=1.0)
