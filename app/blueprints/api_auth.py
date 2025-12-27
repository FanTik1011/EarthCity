from flask import Blueprint, request, jsonify, redirect, current_app, url_for
from flask_login import login_user, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from ..extensions import db, login_manager, oauth
from ..models import User, Country
from ..services.admin import auto_promote_admin, kick_blocked_users
from ..services.mailer import send_confirmation_email

bp_api_auth = Blueprint("api_auth", __name__)

@login_manager.user_loader
def load_user(user_id: str):
    try:
        return db.session.get(User, int(user_id))
    except Exception:
        return None

@bp_api_auth.before_app_request
def _kick_blocked_users():
    return kick_blocked_users()

@bp_api_auth.get("/api/me")
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
        is_blocked=bool(getattr(current_user, "is_blocked", False))
    )

@bp_api_auth.post("/api/register")
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
        password_hash=generate_password_hash(password),
        is_confirmed=False,
        confirmed_at=None,
        starter_granted=True
    )
    db.session.add(user)
    db.session.commit()

    auto_promote_admin(user)
    login_user(user)

    result = send_confirmation_email(user)
    return jsonify(ok=True, sent=result["sent"], dev_link=result["dev_link"], mail_error=result["error"])

@bp_api_auth.post("/api/login")
def api_login():
    data = request.get_json(force=True, silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    user = User.query.filter_by(email=email).first()
    if not user or not user.password_hash or not check_password_hash(user.password_hash, password):
        return jsonify(ok=False, error="Невірний email або пароль."), 401

    if getattr(user, "is_blocked", False):
        return jsonify(ok=False, error="Акаунт заблоковано адміністратором."), 403

    login_user(user)
    auto_promote_admin(user)

    has_country = Country.query.filter_by(owner_user_id=user.id).first() is not None
    return jsonify(
        ok=True,
        is_confirmed=bool(user.is_confirmed),
        username=user.username,
        coins=int(user.coins or 0),
        has_country=bool(has_country),
        starter_granted=bool(getattr(user, "starter_granted", True)),
        is_admin=bool(getattr(user, "is_admin", False)),
        is_blocked=bool(getattr(user, "is_blocked", False))
    )

@bp_api_auth.post("/api/logout")
def api_logout():
    if current_user.is_authenticated:
        logout_user()
    return jsonify(ok=True)

@bp_api_auth.post("/api/resend-confirmation")
def api_resend_confirmation():
    if not current_user.is_authenticated:
        return jsonify(ok=False, error="Not authenticated"), 401
    if current_user.is_confirmed:
        return jsonify(ok=True, already=True, sent=True, dev_link=None, mail_error=None)

    result = send_confirmation_email(current_user)
    return jsonify(ok=True, sent=result["sent"], dev_link=result["dev_link"], mail_error=result["error"])


# ============================================================
# ✅ GOOGLE LOGIN (OAuth2) — NEW
# ============================================================

@bp_api_auth.get("/auth/google")
def auth_google_start():
    # Повернення після логіну:
    # - якщо ти робиш login з globe_auth.html → можна редірект на "/"
    # - можеш передати next=/globe або інше
    next_url = request.args.get("next") or "/"
    session_key = "oauth_next"
    from flask import session
    session[session_key] = next_url

    base = current_app.config.get("PUBLIC_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
    redirect_uri = f"{base}/auth/google/callback"
    return oauth.google.authorize_redirect(redirect_uri)

@bp_api_auth.get("/auth/google/callback")
def auth_google_callback():
    from flask import session

    token = oauth.google.authorize_access_token()

    # userinfo може бути і в token['userinfo'], і як id_token
    userinfo = token.get("userinfo")
    if not userinfo:
        userinfo = oauth.google.parse_id_token(token)

    if not userinfo:
        return redirect("/?google_error=1")

    google_sub = userinfo.get("sub")
    email = (userinfo.get("email") or "").strip().lower()
    name = (userinfo.get("name") or "").strip()
    picture = (userinfo.get("picture") or "").strip()

    if not email or not google_sub:
        return redirect("/?google_error=2")

    # 1) шукаємо існуючого користувача
    user = None

    # якщо додаси поле google_sub — будемо шукати по ньому (найкраще)
    if hasattr(User, "google_sub"):
        user = User.query.filter_by(google_sub=google_sub).first()

    # якщо не знайшли — шукаємо по email
    if not user:
        user = User.query.filter_by(email=email).first()

    # 2) якщо нема — створюємо
    if not user:
        # username має бути унікальний: зробимо з email
        base_username = (email.split("@")[0] or "user").strip()
        username = base_username

        # унікалізація username
        i = 0
        while User.query.filter_by(username=username).first():
            i += 1
            username = f"{base_username}{i}"

        user = User(
            username=username,
            email=email,
            password_hash=None,           # 🔥 Google user без паролю
            is_confirmed=True,            # 🔥 Google email вже підтверджений
            confirmed_at=None,
            starter_granted=True
        )

        # якщо поля існують — запишемо
        if hasattr(user, "google_sub"):
            user.google_sub = google_sub
        if hasattr(user, "avatar_url"):
            user.avatar_url = picture
        if hasattr(user, "full_name"):
            user.full_name = name
        if hasattr(user, "auth_provider"):
            user.auth_provider = "google"

        db.session.add(user)
        db.session.commit()
    else:
        # 3) якщо існує — дописуємо google_sub/аватар (якщо треба)
        changed = False
        if hasattr(user, "google_sub") and not getattr(user, "google_sub", None):
            user.google_sub = google_sub
            changed = True
        if hasattr(user, "avatar_url") and picture and getattr(user, "avatar_url", "") != picture:
            user.avatar_url = picture
            changed = True
        if hasattr(user, "full_name") and name and getattr(user, "full_name", "") != name:
            user.full_name = name
            changed = True
        if hasattr(user, "auth_provider") and getattr(user, "auth_provider", None) != "google":
            user.auth_provider = "google"
            changed = True

        # якщо раптом був не confirmed — зробимо confirmed
        if hasattr(user, "is_confirmed") and not getattr(user, "is_confirmed", False):
            user.is_confirmed = True
            changed = True

        if changed:
            db.session.commit()

    # блокування працює як і було
    if getattr(user, "is_blocked", False):
        return redirect("/?blocked=1")

    login_user(user)
    auto_promote_admin(user)

    next_url = session.pop("oauth_next", None) or "/"
    return redirect(next_url)
