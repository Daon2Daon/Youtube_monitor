"""
YouTube Monitor 독립 앱 - FastAPI 메인 애플리케이션.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import init_db, run_migrations
from app.middleware import AuthMiddleware
from app.routers import auth, youtube as youtube_router
from app.services.scheduler import scheduler_service

app = FastAPI(
    title="YouTube Monitor",
    description="YouTube 채널 모니터링 및 AI 분석 서비스",
    version="1.0.0",
    debug=settings.DEBUG,
)

# 미들웨어 등록 (나중에 등록된 것이 먼저 실행)
app.add_middleware(AuthMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET_KEY,
    max_age=settings.SESSION_MAX_AGE,
    same_site="lax",
    https_only=not settings.DEBUG,
)

YOUTUBE_UI_DIR = Path("static/youtube")


def _youtube_index():
    return FileResponse(YOUTUBE_UI_DIR / "index.html")


@app.get("/static/youtube")
@app.get("/static/youtube/")
async def youtube_spa_index():
    """SPA 진입: React Router basename=/static/youtube"""
    return _youtube_index()


@app.get("/static/youtube/{resource_path:path}")
async def youtube_spa_assets(resource_path: str):
    """에셋 파일은 그대로, 그 외 경로는 index.html (클라이언트 라우팅)"""
    target = YOUTUBE_UI_DIR / resource_path
    if target.is_file():
        return FileResponse(target)
    return _youtube_index()


# Static 파일 서빙 (youtube 외 경로)
app.mount("/static", StaticFiles(directory="static"), name="static")

# API 라우터 등록
app.include_router(auth.router)
app.include_router(youtube_router.router)


@app.get("/health")
async def health_check():
    return JSONResponse(content={"status": "healthy"})


@app.get("/login")
async def login_page():
    from fastapi.responses import HTMLResponse
    import os

    login_html = os.path.join("app", "templates", "login.html")
    if os.path.exists(login_html):
        with open(login_html, encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<form method='post' action='/auth/login'>"
                        "<input name='username' placeholder='Username'>"
                        "<input name='password' type='password' placeholder='Password'>"
                        "<button type='submit'>Login</button></form>")


@app.get("/")
async def index_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/youtube/")


@app.on_event("startup")
async def startup_event():
    print("YouTube Monitor 시작")
    print(f"DEBUG 모드: {settings.DEBUG}")

    # 데이터베이스 초기화 (youtube_settings 테이블)
    init_db()

    # 마이그레이션 실행 (DDL + 시드 + 부트스트랩 env)
    run_migrations()

    # YouTube 데이터 테이블 생성 (aiosqlite)
    try:
        from app.services.youtube.db_engine import db_engine_manager
        await db_engine_manager.ensure_schema()
    except Exception as e:
        print(f"⚠️  YouTube 데이터 테이블 생성 실패: {e}")

    # YouTube 가상 채널 초기화
    try:
        from sqlalchemy.ext.asyncio import async_sessionmaker
        from app.routers.youtube import ensure_instant_channel

        engine = await db_engine_manager.get_engine()
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as sess:
            async with sess.begin():
                await ensure_instant_channel(sess)
        print("✅ YouTube 가상 채널 초기화 완료")
    except Exception as e:
        print(f"⚠️  YouTube 가상 채널 초기화 실패: {e}")

    # 스케줄러 시작
    scheduler_service.start()

    # YouTube Job 등록
    try:
        scheduler_service.setup_youtube_jobs()
    except Exception as e:
        print(f"⚠️  YouTube Job 등록 실패: {e}")

    # 등록된 Job 목록 출력
    jobs = scheduler_service.get_all_jobs()
    if jobs:
        print(f"등록된 Job 목록 ({len(jobs)}개):")
        for job in jobs:
            print(f"   - {job['id']}: 다음 실행 {job['next_run_time']}")
    else:
        print("등록된 Job이 없습니다")


@app.on_event("shutdown")
async def shutdown_event():
    print("YouTube Monitor 종료")
    scheduler_service.shutdown()

    try:
        from app.services.youtube.db_engine import db_engine_manager
        await db_engine_manager.dispose()
    except Exception:
        pass
