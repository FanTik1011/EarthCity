from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from ..extensions import db
from ..models import User
from ..services.admin import admin_required

bp_admin_api = Blueprint("admin_api", __name__)

@bp_admin_api.get("/admin/api/users")
@admin_required
def admin_api_users():
    users = User.query.order_by(User.created_at.desc()).all()
    out = []
    for u in users:
        out.append({
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "coins": int(u.coins or 0),
            "is_confirmed": bool(u.is_confirmed),
            "is_admin": bool(getattr(u, "is_admin", False)),
            "is_blocked": bool(getattr(u, "is_blocked", False)),
            "blocked_reason": u.blocked_reason,
            "blocked_at": u.blocked_at.isoformat() if u.blocked_at else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        })
    return jsonify(ok=True, data=out)

@bp_admin_api.post("/admin/api/users/<int:uid>/block")
@admin_required
def admin_api_block(uid: int):
    data = request.get_json(force=True, silent=True) or {}
    reason = (data.get("reason") or "Blocked by admin").strip()[:255]

    u = db.session.get(User, uid)
    if not u:
        return jsonify(ok=False, error="User not found"), 404
    if u.id == current_user.id:
        return jsonify(ok=False, error="You cannot block yourself"), 400
    if getattr(u, "is_admin", False):
        return jsonify(ok=False, error="You cannot block another admin"), 400

    u.is_blocked = True
    u.blocked_reason = reason
    u.blocked_at = datetime.utcnow()
    db.session.commit()
    return jsonify(ok=True)

@bp_admin_api.post("/admin/api/users/<int:uid>/unblock")
@admin_required
def admin_api_unblock(uid: int):
    u = db.session.get(User, uid)
    if not u:
        return jsonify(ok=False, error="User not found"), 404

    u.is_blocked = False
    u.blocked_reason = None
    u.blocked_at = None
    db.session.commit()
    return jsonify(ok=True)

@bp_admin_api.post("/admin/api/users/<int:uid>/give_coins")
@admin_required
def admin_api_give_coins(uid: int):
    data = request.get_json(force=True, silent=True) or {}
    amount = int(data.get("amount") or 0)

    if amount == 0:
        return jsonify(ok=False, error="amount required"), 400
    if amount < -1_000_000 or amount > 1_000_000:
        return jsonify(ok=False, error="amount too large"), 400

    u = db.session.get(User, uid)
    if not u:
        return jsonify(ok=False, error="User not found"), 404

    new_balance = int(u.coins or 0) + amount
    if new_balance < 0:
        new_balance = 0
    u.coins = new_balance
    db.session.commit()
    return jsonify(ok=True, coins=int(u.coins or 0))
