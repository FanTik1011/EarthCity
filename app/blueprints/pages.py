from datetime import datetime
from flask import Blueprint, render_template, send_from_directory
from flask_login import login_required, current_user
from itsdangerous import BadSignature, SignatureExpired

from ..services.mailer import parse_confirm_token
from ..extensions import db
from ..models import User

bp_pages = Blueprint("pages", __name__)

@bp_pages.get("/")
def globe_page():
    return render_template("globe_auth.html")

@bp_pages.get("/admin")
@login_required
def admin_page():
    if not getattr(current_user, "is_admin", False):
        return ("Forbidden", 403)
    return render_template("admin_panel.html")

@bp_pages.get("/favicon.ico")
def favicon():
    import os
    static_path = os.path.join(bp_pages.root_path, "..", "..", "static")
    static_path = os.path.abspath(static_path)
    if os.path.exists(os.path.join(static_path, "favicon.ico")):
        return send_from_directory(static_path, "favicon.ico")
    return ("", 204)

@bp_pages.get("/confirm/<token>")
def confirm_email(token: str):
    try:
        data = parse_confirm_token(token)
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

    return render_template(
        "confirm_result.html",
        ok=True,
        msg="Email підтверджено ✅ Повернись на вкладку з глобусом і зроби Login (або перезавантаж сторінку)."
    )
# app/blueprints/pages.py
@bp_pages.get("/market")
def page_market():
    return render_template("market.html")
