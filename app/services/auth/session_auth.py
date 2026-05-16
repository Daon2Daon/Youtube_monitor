"""
세션 기반 인증 서비스
관리자 로그인 및 세션 관리를 담당합니다.
"""

import logging
from fastapi import Request, HTTPException
from app.config import settings

logger = logging.getLogger(__name__)


def verify_admin_credentials(username: str, password: str) -> bool:
    return (
        username == settings.ADMIN_USERNAME and
        password == settings.ADMIN_PASSWORD
    )


def create_session(request: Request) -> None:
    request.session["authenticated"] = True
    request.session["username"] = settings.ADMIN_USERNAME


def destroy_session(request: Request) -> None:
    request.session.clear()


def is_authenticated(request: Request) -> bool:
    return request.session.get("authenticated", False)


async def require_auth(request: Request) -> None:
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Not authenticated")
