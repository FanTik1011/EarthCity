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
    PUBLIC_BASE_URL = (os.getenv("PUBLIC_BASE_URL") or "").strip()

    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "1") == "1"

    # Mail
    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "1") == "1"
    MAIL_USE_SSL = os.getenv("MAIL_USE_SSL", "0") == "1"
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", MAIL_USERNAME or "no-reply@example.com")

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # Economy
    START_COINS = int(os.getenv("START_COINS", "5000"))

    COUNTRY_BASE_COST = int(os.getenv("COUNTRY_BASE_COST", "800"))
    COUNTRY_COST_PER_1000_KM2 = int(os.getenv("COUNTRY_COST_PER_1000_KM2", "35"))
    COUNTRY_MAX_AREA_KM2 = int(os.getenv("COUNTRY_MAX_AREA_KM2", "250000"))
    COUNTRY_MAX_POINTS = int(os.getenv("COUNTRY_MAX_POINTS", "60"))
    COUNTRY_MIN_POINTS = int(os.getenv("COUNTRY_MIN_POINTS", "3"))

    FACTORY_PLACE_FEE = int(os.getenv("FACTORY_PLACE_FEE", "120"))
    FACTORY_MAX_PER_COUNTRY = int(os.getenv("FACTORY_MAX_PER_COUNTRY", "40"))
    FACTORY_ACCUM_CAP_HOURS = int(os.getenv("FACTORY_ACCUM_CAP_HOURS", "72"))
    FACTORY_PICK_RADIUS_KM = int(os.getenv("FACTORY_PICK_RADIUS_KM", "120"))

    TOKEN_MAX_AGE_SECONDS = int(os.getenv("TOKEN_MAX_AGE_SECONDS", str(60 * 60 * 24)))
