import logging
from sqlalchemy import text as sa_text
from .extensions import db

log = logging.getLogger("earthcity")

def _ensure_user_columns_sqlite():
    """
    SQLite only: add new columns if DB already existed.
    Safe ALTER TABLE with checks.
    """
    try:
        cols = [r[1] for r in db.session.execute(sa_text("PRAGMA table_info(user)")).fetchall()]
        alters = []
        if "is_admin" not in cols:
            alters.append("ALTER TABLE user ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0")
        if "is_blocked" not in cols:
            alters.append("ALTER TABLE user ADD COLUMN is_blocked BOOLEAN NOT NULL DEFAULT 0")
        if "blocked_reason" not in cols:
            alters.append("ALTER TABLE user ADD COLUMN blocked_reason VARCHAR(255)")
        if "blocked_at" not in cols:
            alters.append("ALTER TABLE user ADD COLUMN blocked_at DATETIME")

        for sql in alters:
            db.session.execute(sa_text(sql))
        if alters:
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        log.warning("DB migrate (sqlite) skipped/failed: %s", e)

def init_db(app):
    with app.app_context():
        db.create_all()
        uri = (app.config.get("SQLALCHEMY_DATABASE_URI") or "")
        if uri.startswith("sqlite"):
            _ensure_user_columns_sqlite()
