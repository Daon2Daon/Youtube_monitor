"""
간단한 사용자 데이터 클래스.
Telegram 발송에 필요한 chat_id를 담는 경량 모델.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class User:
    """Telegram 발송에 필요한 최소 사용자 정보."""
    user_id: int = 0
    telegram_chat_id: Optional[str] = None
