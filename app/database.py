"""
데이터베이스 연결 및 세션 관리
SQLAlchemy를 사용한 SQLite 데이터베이스 설정
youtube_settings + YouTube 데이터 테이블을 하나의 SQLite 파일에서 관리합니다.
"""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings

SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=settings.DEBUG,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """데이터베이스 초기화: 모든 테이블 생성."""
    from app.models import youtube_setting  # noqa: F401
    Base.metadata.create_all(bind=engine)
    print("✅ 데이터베이스 테이블(youtube_settings) 생성/확인 완료")


def _migrations_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "migrations"


def _sqlite_table_exists(cursor, name: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    )
    return cursor.fetchone() is not None


def _youtube_setting_row_is_empty(cursor, category: str, key: str) -> bool:
    cursor.execute(
        "SELECT value, value_enc, is_secret FROM youtube_settings WHERE category = ? AND key = ?",
        (category, key),
    )
    row = cursor.fetchone()
    if not row:
        return False
    value, value_enc, is_secret = row[0], row[1], int(row[2] or 0)
    if is_secret:
        return value_enc is None or (isinstance(value_enc, bytes) and len(value_enc) == 0)
    return value is None or value == ""


def _apply_bootstrap_from_env(conn, cursor) -> None:
    """YOUTUBE_BOOTSTRAP_* 환경변수를 비어 있는 행에만 반영 (비밀은 Fernet)."""
    from cryptography.fernet import Fernet
    from app.config import settings as app_settings

    fernet = None
    key_str = (app_settings.YOUTUBE_SETTINGS_FERNET_KEY or "").strip()
    if key_str:
        try:
            fernet = Fernet(key_str.encode("utf-8"))
        except Exception as e:
            print(f"⚠️  YOUTUBE_SETTINGS_FERNET_KEY가 유효하지 않습니다: {e}")

    def update_plain(category: str, key: str, val: str) -> None:
        cursor.execute(
            "UPDATE youtube_settings SET value = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE category = ? AND key = ?",
            (val, category, key),
        )

    def update_secret(category: str, key: str, val: str) -> None:
        if not fernet:
            print("⚠️  YouTube bootstrap: 비밀 필드 저장을 건너뜁니다 (Fernet 키 없음)")
            return
        enc = fernet.encrypt(val.encode("utf-8"))
        cursor.execute(
            "UPDATE youtube_settings SET value = NULL, value_enc = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE category = ? AND key = ?",
            (enc, category, key),
        )

    bootstrap_plain = [
        ("ai_gateway", "base_url", app_settings.YOUTUBE_BOOTSTRAP_LITELLM_BASE_URL),
        ("ai_gateway", "primary_model", app_settings.YOUTUBE_BOOTSTRAP_PRIMARY_MODEL),
        ("ai_gateway", "fallback_model", app_settings.YOUTUBE_BOOTSTRAP_FALLBACK_MODEL),
        ("ai_gateway", "tagging_model", app_settings.YOUTUBE_BOOTSTRAP_TAGGING_MODEL),
    ]
    bootstrap_secret = [
        ("ai_gateway", "api_key", app_settings.YOUTUBE_BOOTSTRAP_LITELLM_API_KEY),
        ("polling", "youtube_api_key", app_settings.YOUTUBE_BOOTSTRAP_YOUTUBE_API_KEY),
    ]

    for category, key, val in bootstrap_plain:
        if not (val and str(val).strip()):
            continue
        if _youtube_setting_row_is_empty(cursor, category, key):
            update_plain(category, key, str(val).strip())

    for category, key, val in bootstrap_secret:
        if not (val and str(val).strip()):
            continue
        if _youtube_setting_row_is_empty(cursor, category, key):
            update_secret(category, key, str(val).strip())


def run_migrations():
    """마이그레이션 실행: youtube_settings 테이블 생성 및 시드 적용."""
    import sqlite3

    db_path = Path(SQLALCHEMY_DATABASE_URL.replace("sqlite:///", ""))

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # youtube_settings 테이블
        mig_dir = _migrations_dir()
        ddl_path = mig_dir / "000_sqlite_settings.sql"
        seed_path = mig_dir / "000_seed_settings.sql"

        if ddl_path.is_file() and not _sqlite_table_exists(cursor, "youtube_settings"):
            print("🔄 마이그레이션: youtube_settings 테이블 생성")
            cursor.executescript(ddl_path.read_text(encoding="utf-8"))
            conn.commit()

        if seed_path.is_file():
            print("🔄 YouTube 설정 시드 적용 (INSERT OR IGNORE)")
            cursor.executescript(seed_path.read_text(encoding="utf-8"))
            conn.commit()

        _apply_bootstrap_from_env(conn, cursor)
        conn.commit()

        conn.close()
        print("✅ youtube_settings 마이그레이션 완료")

    except Exception as e:
        print(f"⚠️  마이그레이션 오류: {e}")
