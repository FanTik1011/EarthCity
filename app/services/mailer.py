import logging
from urllib.parse import urljoin
from datetime import datetime
from itsdangerous import URLSafeTimedSerializer
from flask import current_app, request, url_for, render_template
from flask_mail import Message
from ..extensions import mail, db

log = logging.getLogger("earthcity")

TOKEN_MAX_AGE_SECONDS = int(
    __import__("os").getenv("TOKEN_MAX_AGE_SECONDS", str(60 * 60 * 24))
)

def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        secret_key=current_app.config["SECRET_KEY"],
        salt=current_app.config["SECURITY_SALT"]
    )

def make_confirm_token(user) -> str:
    return _serializer().dumps({"uid": user.id, "email": user.email})

def parse_confirm_token(token: str):
    return _serializer().loads(token, max_age=TOKEN_MAX_AGE_SECONDS)

def absolute_url(path: str) -> str:
    base = (current_app.config.get("PUBLIC_BASE_URL") or "").rstrip("/")
    if base:
        return urljoin(base + "/", path.lstrip("/"))

    base2 = request.host_url
    if base2.startswith("http://"):
        base2 = base2.replace("http://", "https://", 1)
    return urljoin(base2, path.lstrip("/"))

def send_confirmation_email(user) -> dict:
    token = make_confirm_token(user)
    link = absolute_url(url_for("pages.confirm_email", token=token))

    if not current_app.config["MAIL_USERNAME"] or not current_app.config["MAIL_PASSWORD"]:
        log.warning("[MAIL] Missing creds. DEV link: %s", link)
        return {"sent": False, "dev_link": link, "error": "MAIL creds missing"}

    try:
        html = render_template("email_confirm.html", username=user.username, link=link)
        msg = Message(
            subject="Підтвердження email — EarthCity",
            recipients=[user.email],
            html=html,
            sender=current_app.config["MAIL_DEFAULT_SENDER"]
        )
        mail.send(msg)
        return {"sent": True, "dev_link": None, "error": None}
    except Exception as e:
        log.exception("[MAIL ERROR] %s", repr(e))
        return {"sent": False, "dev_link": link, "error": str(e)}
