"""
YouTube Monitor 앱용 SQLite 설정 테이블
AI Gateway·폴링·알림 등 런타임 설정의 저장소
"""

from sqlalchemy import Column, DateTime, Integer, LargeBinary, String, UniqueConstraint, func

from app.database import Base


class YoutubeSetting(Base):
    """youtube_settings — 카테고리/키 기반 키-값(+ 선택적 암호화)"""

    __tablename__ = "youtube_settings"
    __table_args__ = (
        UniqueConstraint("category", "key", name="uq_youtube_settings_category_key"),
    )

    setting_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    category = Column(String, nullable=False)
    key = Column(String, nullable=False)
    value = Column(String, nullable=True)
    value_enc = Column(LargeBinary, nullable=True)
    value_type = Column(String, nullable=False, default="string")
    is_secret = Column(Integer, nullable=False, default=0)
    description = Column(String, nullable=True)
    updated_at = Column(DateTime, nullable=True, server_default=func.current_timestamp())

    def __repr__(self):
        return f"<YoutubeSetting(category={self.category!r}, key={self.key!r})>"
