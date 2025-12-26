import logging
from functools import wraps
from flask import request, jsonify
from flask_login import current_user, logout_user
from ..extensions import db

log = logging.getLogger("earthcity")

HARDCODE_ADMIN_EMAILS = {
    "volodakotlarov191@gmail.com",
}

def auto_promote_admin(user):
    """
    Make user admin automatically if their email is in HARDCODE_ADMIN_EMAILS.
    Safe: affects only your email(s).
    """
    try:
        if not user or not getattr(user, "email", None):
            return
        if user.email.strip().lower() in HARDCODE_ADMIN_EMAILS and not getattr(user, "is_admin", False):
            user.is_admin = True
            db.session.commit()
    except Exception:
        db.session.rollback()

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify(ok=False, error="Not authenticated"), 401
        if getattr(current_user, "is_blocked", False):
            logout_user()
            return jsonify(ok=False, error="Blocked"), 403
        if not getattr(current_user, "is_admin", False):
            return jsonify(ok=False, error="Admin only"), 403
        return fn(*args, **kwargs)
    return wrapper

def kick_blocked_users():
    if current_user.is_authenticated and getattr(current_user, "is_blocked", False):
        logout_user()
        if request.path.startswith("/api/") or request.path.startswith("/admin/api/"):
            return jsonify(ok=False, error="Blocked"), 403
    return None
