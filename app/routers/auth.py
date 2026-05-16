"""
YouTube Monitor - 인증 API 라우터.

관리자 세션 로그인/로그아웃 + Telegram Chat ID 설정 엔드포인트.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.youtube_setting import YoutubeSetting
from app.services.auth.session_auth import (
    create_session,
    destroy_session,
    is_authenticated,
    verify_admin_credentials,
)
from app.services.youtube.settings_manager import get_youtube_settings_manager

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _settings_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────────────────────
# 관리자 세션 로그인
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/login")
async def admin_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    """관리자 로그인 (세션 기반)."""
    if verify_admin_credentials(username, password):
        create_session(request)
        return RedirectResponse(url="/", status_code=303)
    return RedirectResponse(url="/login?error=1", status_code=303)


@router.post("/logout")
async def admin_logout(request: Request):
    """관리자 로그아웃."""
    destroy_session(request)
    return RedirectResponse(url="/login", status_code=303)


@router.get("/session/status")
async def session_status(request: Request):
    """현재 세션 인증 상태 확인."""
    authenticated = is_authenticated(request)
    username = request.session.get("username") if authenticated else None
    return JSONResponse(content={"authenticated": authenticated, "username": username})


# ──────────────────────────────────────────────────────────────────────────────
# Telegram 설정
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/telegram/status")
async def telegram_status():
    """현재 Telegram Chat ID 설정 상태 확인."""
    mgr = get_youtube_settings_manager()
    notif_cfg = mgr.get_notification()
    chat_id = (notif_cfg.telegram_chat_id or "").strip()
    return JSONResponse(
        content={
            "telegram_connected": bool(chat_id),
            "chat_id": chat_id or None,
        }
    )


@router.post("/telegram/configure")
async def telegram_configure(
    chat_id: str = Form(...),
    db: Session = Depends(_settings_db),
):
    """Telegram Chat ID를 youtube_settings.notification 테이블에 저장."""
    chat_id = (chat_id or "").strip()
    if not chat_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chat ID를 입력해주세요.",
        )

    row = (
        db.query(YoutubeSetting)
        .filter(
            YoutubeSetting.category == "notification",
            YoutubeSetting.key == "telegram_chat_id",
        )
        .first()
    )
    if row is None:
        row = YoutubeSetting(category="notification", key="telegram_chat_id")
        db.add(row)
    row.value = chat_id
    row.value_type = "string"
    row.is_secret = 0
    row.updated_at = datetime.now(timezone.utc)
    db.commit()

    mgr = get_youtube_settings_manager()
    mgr.invalidate("notification")

    return JSONResponse(
        content={"message": "Telegram Chat ID 저장 완료", "chat_id": chat_id}
    )


@router.post("/telegram/test")
async def telegram_test():
    """저장된 Chat ID로 테스트 메시지 발송."""
    from app.models.user import User
    from app.services.notification.telegram_sender import telegram_sender

    mgr = get_youtube_settings_manager()
    notif_cfg = mgr.get_notification()
    chat_id = (notif_cfg.telegram_chat_id or "").strip()

    if not chat_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telegram Chat ID가 설정되지 않았습니다.",
        )

    user = User(user_id=0, telegram_chat_id=chat_id)
    ok = await telegram_sender.send_message(
        user, "YouTube Monitor 텔레그램 연동 테스트 메시지입니다."
    )

    if not ok:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="메시지 발송 실패",
        )

    return JSONResponse(
        content={"message": "테스트 메시지 발송 성공", "chat_id": chat_id}
    )
