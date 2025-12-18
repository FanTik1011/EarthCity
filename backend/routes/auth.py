from flask import Blueprint, request, jsonify
from flask_login import login_user, logout_user, current_user

from models import db
from models.user import User

auth_bp = Blueprint("auth_bp", __name__)

@auth_bp.get("/api/me")
def api_me():
    if not current_user.is_authenticated:
        return jsonify({"authenticated": False})

    return jsonify({
        "authenticated": True,
        "user": {
            "id": current_user.id,
            "username": current_user.username,
            "role": current_user.role,
            "balance": current_user.balance
        }
    })

@auth_bp.post("/api/auth/register")
def register():
    data = request.get_json(force=True, silent=True) or {}
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip() or None
    password = data.get("password") or ""

    if len(username) < 3 or len(username) > 40:
        return jsonify({"error": "username length 3..40"}), 400
    if len(password) < 4:
        return jsonify({"error": "password too short"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "username already taken"}), 409

    u = User(username=username, email=email)
    u.set_password(password)

    db.session.add(u)
    db.session.commit()

    login_user(u)
    return jsonify({"ok": True}), 201

@auth_bp.post("/api/auth/login")
def login():
    data = request.get_json(force=True, silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    u = User.query.filter_by(username=username).first()
    if not u or not u.check_password(password):
        return jsonify({"error": "invalid credentials"}), 401

    login_user(u)
    return jsonify({"ok": True})

@auth_bp.post("/api/auth/logout")
def logout():
    if current_user.is_authenticated:
        logout_user()
    return jsonify({"ok": True})
