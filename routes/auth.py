from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user

from models import db
from models.user import User

auth_bp = Blueprint("auth_bp", __name__)
login_manager = LoginManager()

@login_manager.user_loader
def load_user(user_id: str):
    return User.query.get(int(user_id))

@auth_bp.post("/api/auth/register")
def register_local():
    data = request.get_json(force=True, silent=True) or {}
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({"error": "username and password required"}), 400

    if len(username) < 3 or len(username) > 24:
        return jsonify({"error": "username must be 3-24 chars"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "username already exists"}), 409

    if email and User.query.filter_by(email=email).first():
        return jsonify({"error": "email already exists"}), 409

    u = User(
        username=username,
        email=email or None,
        password_hash=generate_password_hash(password),
        role="worker"
    )
    db.session.add(u)
    db.session.commit()

    login_user(u)
    return jsonify({"ok": True, "user": {"id": u.id, "username": u.username, "role": u.role}}), 201

@auth_bp.post("/api/auth/login")
def login_local():
    data = request.get_json(force=True, silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    u = User.query.filter_by(username=username).first()
    if not u or not u.password_hash or not check_password_hash(u.password_hash, password):
        return jsonify({"error": "invalid credentials"}), 401

    login_user(u)
    return jsonify({"ok": True, "user": {"id": u.id, "username": u.username, "role": u.role}})

@auth_bp.post("/api/auth/logout")
@login_required
def logout():
    logout_user()
    return jsonify({"ok": True})

@auth_bp.get("/api/me")
def me():
    if not current_user.is_authenticated:
        return jsonify({"authenticated": False})
    return jsonify({
        "authenticated": True,
        "user": {"id": current_user.id, "username": current_user.username, "role": current_user.role}
    })
