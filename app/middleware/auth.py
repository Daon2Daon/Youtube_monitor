"""
인증 미들웨어
세션 기반 인증을 통해 보호된 경로에 대한 접근을 제어합니다.
"""

from fastapi import Request
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


EXCLUDE_PATHS = [
    "/login",
    "/auth/login",
    "/static",
    "/favicon.ico",
    "/health",
]


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if any(path.startswith(p) for p in EXCLUDE_PATHS):
            return await call_next(request)

        is_authenticated = request.session.get("authenticated", False)

        if not is_authenticated:
            if path.startswith("/api/"):
                return JSONResponse(
                    {"detail": "Not authenticated"},
                    status_code=401,
                )
            return RedirectResponse(url="/login", status_code=303)

        return await call_next(request)
