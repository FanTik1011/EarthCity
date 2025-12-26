import os

def _normalize_db_url(raw: str) -> str:
    if not raw:
        return "sqlite:///app.db"
    if raw.startswith("postgres://"):
        return raw.replace("postgres://", "postgresql://", 1)
    return raw

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev_change_me")
    SECURITY_SALT = os.getenv("SECURITY_SALT", "dev_salt_change_me")

    SQLALCHEMY_DATABASE_URI = _normalize_db_url(os.getenv("DATABASE_URL", "sqlite:///app.db"))
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    PREFERRED_URL_SCHEME = os.getenv("PREFERRED_URL_SCHEME", "https")

    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "1") == "1"

    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "1") == "1"
    MAIL_USE_SSL = os.getenv("MAIL_USE_SSL", "0") == "1"
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", MAIL_USERNAME or "no-reply@example.com")

    PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip()
