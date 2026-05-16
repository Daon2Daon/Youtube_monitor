"""
YouTube 모니터 독립 앱: 단일 SQLite 전용 Declarative Base.
모든 YouTube 데이터 테이블(channels, videos, video_analysis, tags, video_tags, job_logs)이
이 Base를 공유합니다.
"""

from sqlalchemy.orm import declarative_base

YoutubeBase = declarative_base()
