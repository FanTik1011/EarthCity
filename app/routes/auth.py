from datetime import datetime
from itsdangerous import BadSignature, SignatureExpired

from flask import Blueprint, jsonify, request, render_template, current_app
from flask_login import login_user, logout_user, current_user

from ..extensions import db, mail
from ..models import User, Country
from ..services.tokens import make_serializer
from ..services.mailer import send_confirmation_email

auth_bp = Blueprint("auth_bp", __name__)

@auth_bp.get("/api/me")
def api_me():
    if not current_user.is_authenticated:
        return jsonify(
            authenticated=False,
            username=None,
            email=None,
            is_confirmed=False,
            coins=0,
            has_country=False,
            starter_granted=False,
            is_admin=False,
            is_blocked=False
        )

    has_country = Country.query.filter_by(owner_user_id=current_user.id).first() is not None
    return jsonify(
        authenticated=True,
        username=current_user.username,
        email=current_user.email,
        is_confirmed=bool(current_user.is_confirmed),
        coins=int(current_user.coins or 0),
        has_country=bool(has_country),
        starter_granted=bool(getattr(current_user, "starter_granted", True)),
        is_admin=bool(getattr(current_user, "is_admin", False)),
        is_blocked=bool(getattr(current_user, "is_blocked", False)),
    )

@auth_bp.post("/api/register")
def api_register():
    data = request.get_json(force=True, silent=True) or {}

    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if len(username) < 3:
        return jsonify(ok=False, error="Username мінімум 3 символи."), 400
    if "@" not in email or "." not in email:
        return jsonify(ok=False, error="Некоректний email."), 400
    if len(password) < 6:
        return jsonify(ok=False, error="Пароль мінімум 6 символів."), 400

    if User.query.filter_by(username=username).first():
        return jsonify(ok=False, error="Такий username вже існує."), 409
    if User.query.filter_by(email=email).first():
        return jsonify(ok=False, error="Такий email вже зареєстрований."), 409

    user = User(
        username=username,
        email=email,
        is_confirmed=False,
        confirmed_at=None,
        coins=current_app.config["START_COINS"],
        starter_granted=True
    )
    user.set_password(password)

    db.session.add(user)
    db.session.commit()

    login_user(user)

    result = send_confirmation_email(current_app, mail, user, current_app.config["TOKEN_MAX_AGE_SECONDS"])
    return jsonify(ok=True, sent=result["sent"], dev_link=result["dev_link"], mail_error=result["error"])

@auth_bp.post("/api/login")
def api_login():
    data = request.get_json(force=True, silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify(ok=False, error="Невірний email або пароль."), 401

    if getattr(user, "is_blocked", False):
        return jsonify(ok=False, error="Акаунт заблокований адміністратором."), 403

    login_user(user)

    has_country = Country.query.filter_by(owner_user_id=user.id).first() is not None
    return jsonify(
        ok=True,
        is_confirmed=bool(user.is_confirmed),
        username=user.username,
        coins=int(user.coins or 0),
        has_country=bool(has_country),
        starter_granted=bool(getattr(user, "starter_granted", True))
    )

@auth_bp.post("/api/logout")
def api_logout():
    if current_user.is_authenticated:
        logout_user()
    return jsonify(ok=True)

@auth_bp.post("/api/resend-confirmation")
def api_resend_confirmation():
    if not current_user.is_authenticated:
        return jsonify(ok=False, error="Not authenticated"), 401
    if current_user.is_confirmed:
        return jsonify(ok=True, already=True, sent=True, dev_link=None, mail_error=None)

    result = send_confirmation_email(current_app, mail, current_user, current_app.config["TOKEN_MAX_AGE_SECONDS"])
    return jsonify(ok=True, sent=result["sent"], dev_link=result["dev_link"], mail_error=result["error"])

@auth_bp.get("/confirm/<token>")
def confirm_email(token: str):
    s = make_serializer(current_app.config["SECRET_KEY"], current_app.config["SECURITY_SALT"])
    try:
        data = s.loads(token, max_age=current_app.config["TOKEN_MAX_AGE_SECONDS"])
    except SignatureExpired:
        return render_template("confirm_result.html", ok=False, msg="Токен прострочений. Натисни Resend на сторінці.")
    except BadSignature:
        return render_template("confirm_result.html", ok=False, msg="Невірний токен.")

    user = db.session.get(User, int(data.get("uid", 0)))
    if not user or user.email != data.get("email"):
        return render_template("confirm_result.html", ok=False, msg="Користувача не знайдено або email не співпадає.")

    if not user.is_confirmed:
        user.is_confirmed = True
        user.confirmed_at = datetime.utcnow()
        db.session.commit()

    return render_template("confirm_result.html", ok=True, msg="Email підтверджено ✅ Повернись на вкладку з глобусом і зроби Login (або перезавантаж сторінку).")
