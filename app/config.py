"""
YouTube Monitor 독립 앱 설정 관리
환경변수를 로드하고 전역 설정을 제공합니다.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """애플리케이션 설정 클래스"""

    # Telegram Bot
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")

    # Database (SQLite)
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./data/youtube_monitor.db")

    # App
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"

    # Admin Login
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")
    SESSION_SECRET_KEY: str = os.getenv(
        "SESSION_SECRET_KEY", "change-this-to-random-32-chars-min"
    )
    SESSION_MAX_AGE: int = int(os.getenv("SESSION_MAX_AGE", "86400"))  # 24시간

    # YouTube monitor: SQLite 설정 암호화 (Fernet, 32바이트 url-safe base64)
    YOUTUBE_SETTINGS_FERNET_KEY: str = os.getenv("YOUTUBE_SETTINGS_FERNET_KEY", "")

    # YouTube monitor: 첫 기동 시 빈 youtube_settings 행에만 주입 (이미 값이 있으면 덮어쓰지 않음)
    YOUTUBE_BOOTSTRAP_LITELLM_BASE_URL: str = os.getenv(
        "YOUTUBE_BOOTSTRAP_LITELLM_BASE_URL", ""
    )
    YOUTUBE_BOOTSTRAP_LITELLM_API_KEY: str = os.getenv(
        "YOUTUBE_BOOTSTRAP_LITELLM_API_KEY", ""
    )
    YOUTUBE_BOOTSTRAP_PRIMARY_MODEL: str = os.getenv(
        "YOUTUBE_BOOTSTRAP_PRIMARY_MODEL", ""
    )
    YOUTUBE_BOOTSTRAP_FALLBACK_MODEL: str = os.getenv(
        "YOUTUBE_BOOTSTRAP_FALLBACK_MODEL", ""
    )
    YOUTUBE_BOOTSTRAP_TAGGING_MODEL: str = os.getenv(
        "YOUTUBE_BOOTSTRAP_TAGGING_MODEL", ""
    )
    YOUTUBE_BOOTSTRAP_YOUTUBE_API_KEY: str = os.getenv(
        "YOUTUBE_BOOTSTRAP_YOUTUBE_API_KEY", ""
    )


# 전역 설정 인스턴스
settings = Settings()
