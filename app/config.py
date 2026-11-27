import os
import re
from dotenv import load_dotenv

load_dotenv()


def _db_url():
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return "sqlite:///clinicare.db"
    # Force le pilote psycopg2 (installé via requirements.txt), quelle que soit l'écriture de l'URL
    # (postgres://, postgresql://, postgresql+psycopg://...) et la version de SQLAlchemy.
    return re.sub(r"^postgres(ql)?(\+\w+)?://", "postgresql+psycopg2://", url)


def _engine_options():
    # Sur Vercel (serverless) + pooler Supabase en mode transaction : pas de pool côté application.
    if os.environ.get("VERCEL"):
        from sqlalchemy.pool import NullPool
        return {"poolclass": NullPool}
    return {"pool_pre_ping": True}


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI = _db_url()
    SQLALCHEMY_ENGINE_OPTIONS = _engine_options()
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = bool(os.environ.get("VERCEL"))
    PERMANENT_SESSION_LIFETIME = 60 * 60  # expire after 60 min of inactivity
    SESSION_REFRESH_EACH_REQUEST = True
    WTF_CSRF_TIME_LIMIT = None
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "587"))
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_FROM = os.environ.get("MAIL_FROM", "clinicare@example.com")
    SLOT_MINUTES = 30
    DAY_START = 8
    DAY_END = 17
    LUNCH = (12, 14)

    # Identité de la clinique affichée sur le site public (à adapter)
    CLINIC_NAME = os.environ.get("CLINIC_NAME", "CliniCare")
    CLINIC_CITY = os.environ.get("CLINIC_CITY", "Bujumbura")
    CLINIC_PHONE = os.environ.get("CLINIC_PHONE", "+257 00 00 00 00")
    CLINIC_EMAIL = os.environ.get("CLINIC_EMAIL", "contact@clinicare.bi")
    CLINIC_ADDRESS = os.environ.get("CLINIC_ADDRESS", "Avenue de la clinique, Bujumbura, Burundi")
    CLINIC_HOURS = os.environ.get("CLINIC_HOURS", "Lundi au samedi, 8h00 à 17h00")
