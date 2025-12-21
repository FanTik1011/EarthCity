import os
from datetime import datetime
from werkzeug.security import generate_password_hash

def ensure_admin_from_env(User, db, logger):
    admin_email = (os.getenv("ADMIN_EMAIL") or "").strip().lower()
    admin_username = (os.getenv("ADMIN_USERNAME") or "admin").strip()
    admin_password = os.getenv("ADMIN_PASSWORD") or ""
    reset = os.getenv("ADMIN_RESET_PASSWORD", "0") == "1"

    if not admin_email or not admin_password:
        return

    u = User.query.filter_by(email=admin_email).first()
    if not u:
        u = User(
            username=admin_username,
            email=admin_email,
            password_hash=generate_password_hash(admin_password),
            is_confirmed=True,
            confirmed_at=datetime.utcnow(),
            coins=int(os.getenv("START_COINS", "5000")),
            starter_granted=True,
            is_admin=True,
            is_blocked=False
        )
        db.session.add(u)
        db.session.commit()
        logger.info("[ADMIN] Created admin %s", admin_email)
        return

    changed = False
    if not getattr(u, "is_admin", False):
        u.is_admin = True
        changed = True

    if getattr(u, "is_blocked", False):
        u.is_blocked = False
        u.blocked_reason = None
        u.blocked_at = None
        changed = True

    if reset:
        u.password_hash = generate_password_hash(admin_password)
        changed = True

    if changed:
        db.session.commit()
        logger.info("[ADMIN] Updated admin %s", admin_email)
