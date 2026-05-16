"""
텔레그램 메시지 발송 모듈
Telegram Bot API를 사용한 메시지 발송
"""

import asyncio
from typing import Dict, Optional

import httpx

from app.config import settings
from app.models.user import User


def _telegram_retry_after_sec(response: httpx.Response) -> Optional[float]:
    try:
        payload = response.json()
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    params = payload.get("parameters")
    if isinstance(params, dict) and "retry_after" in params:
        try:
            return float(params["retry_after"])
        except (TypeError, ValueError):
            return None
    return None


class TelegramSender:
    def __init__(self):
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    async def send_message(self, user: User, message: str) -> bool:
        try:
            if not user.telegram_chat_id:
                print("❌ 텔레그램 chat_id가 없습니다")
                return False

            url = f"{self.base_url}/sendMessage"
            data = {
                "chat_id": user.telegram_chat_id,
                "text": message,
                "parse_mode": "HTML",
            }

            timeout = httpx.Timeout(60.0, connect=15.0)
            max_attempts = 4
            backoff_sec = (1.0, 3.0, 8.0)

            for attempt in range(max_attempts):
                try:
                    async with httpx.AsyncClient(timeout=timeout) as client:
                        response = await client.post(url, json=data)

                    if response.status_code == 200:
                        print(f"✅ 텔레그램 메시지 발송 성공 (chat_id: {user.telegram_chat_id})")
                        return True

                    retry_after = _telegram_retry_after_sec(response)
                    if response.status_code == 429 and attempt < max_attempts - 1:
                        wait = retry_after if retry_after is not None else backoff_sec[attempt]
                        print(f"⚠️ 텔레그램 rate limit(429), {wait:.1f}s 후 재시도")
                        await asyncio.sleep(wait)
                        continue

                    if response.status_code >= 500 and attempt < max_attempts - 1:
                        wait = backoff_sec[min(attempt, len(backoff_sec) - 1)]
                        print(f"⚠️ 텔레그램 서버 오류({response.status_code}), {wait:.1f}s 후 재시도")
                        await asyncio.sleep(wait)
                        continue

                    print(f"❌ 텔레그램 메시지 발송 실패: {response.status_code} - {response.text}")
                    return False

                except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as e:
                    if attempt < max_attempts - 1:
                        wait = backoff_sec[min(attempt, len(backoff_sec) - 1)]
                        print(f"⚠️ 텔레그램 전송 일시 오류 ({type(e).__name__}), {wait:.1f}s 후 재시도")
                        await asyncio.sleep(wait)
                        continue
                    print(f"❌ 텔레그램 메시지 발송 실패: {e}")
                    return False

            return False

        except Exception as e:
            print(f"❌ 텔레그램 메시지 발송 실패: {e}")
            return False

    async def get_bot_info(self) -> Optional[Dict]:
        try:
            url = f"{self.base_url}/getMe"
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"❌ 텔레그램 봇 정보 조회 실패: {e}")
            return None

    def is_available(self, user: User) -> bool:
        return user.telegram_chat_id is not None and user.telegram_chat_id != ""


telegram_sender = TelegramSender()
