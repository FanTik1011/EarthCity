from functools import wraps
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required, current_user

from ..extensions import db
from ..models import User

admin_bp = Blueprint("admin_bp", __name__)

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify(ok=False, error="Not authenticated"), 401
        if getattr(current_user, "is_blocked", False):
            return jsonify(ok=False, error="User blocked"), 403
        if not getattr(current_user, "is_admin", False):
            return jsonify(ok=False, error="Admin only"), 403
        return fn(*args, **kwargs)
    return wrapper

@admin_bp.get("/admin")
@login_required
def admin_page():
    if getattr(current_user, "is_blocked", False):
        return ("Blocked", 403)
    if not getattr(current_user, "is_admin", False):
        return ("Forbidden", 403)
    return render_template("admin.html")

@admin_bp.get("/api/admin/users")
@admin_required
def api_admin_users():
    users = User.query.order_by(User.created_at.desc()).all()
    out = []
    for u in users:
        out.append({
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "is_confirmed": bool(u.is_confirmed),
            "coins": int(u.coins or 0),
            "is_admin": bool(getattr(u, "is_admin", False)),
            "is_blocked": bool(getattr(u, "is_blocked", False)),
            "blocked_reason": getattr(u, "blocked_reason", None),
            "created_at": (u.created_at.isoformat() if u.created_at else None)
        })
    return jsonify(ok=True, data=out)

@admin_bp.post("/api/admin/users/<int:uid>/block")
@admin_required
def api_admin_block_user(uid: int):
    if current_user.id == uid:
        return jsonify(ok=False, error="You cannot block yourself."), 400

    data = request.get_json(force=True, silent=True) or {}
    reason = (data.get("reason") or "Без причини").strip()[:255]

    u = db.session.get(User, uid)
    if not u:
        return jsonify(ok=False, error="User not found"), 404

    u.is_blocked = True
    u.blocked_reason = reason
    u.blocked_at = datetime.utcnow()
    db.session.commit()
    return jsonify(ok=True)

@admin_bp.post("/api/admin/users/<int:uid>/unblock")
@admin_required
def api_admin_unblock_user(uid: int):
    u = db.session.get(User, uid)
    if not u:
        return jsonify(ok=False, error="User not found"), 404

    u.is_blocked = False
    u.blocked_reason = None
    u.blocked_at = None
    db.session.commit()
    return jsonify(ok=True)

@admin_bp.post("/api/admin/users/<int:uid>/toggle-admin")
@admin_required
def api_admin_toggle_admin(uid: int):
    if current_user.id == uid:
        return jsonify(ok=False, error="You cannot change your own admin flag here."), 400

    u = db.session.get(User, uid)
    if not u:
        return jsonify(ok=False, error="User not found"), 404

    u.is_admin = not bool(getattr(u, "is_admin", False))
    db.session.commit()
    return jsonify(ok=True, is_admin=bool(u.is_admin))
