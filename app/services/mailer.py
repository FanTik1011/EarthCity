from flask import render_template, url_for, request
from flask_mail import Message
from urllib.parse import urljoin

from .tokens import make_serializer

def absolute_url(public_base_url: str, path: str) -> str:
    base = (public_base_url or "").rstrip("/")
    if base:
        return urljoin(base + "/", path.lstrip("/"))

    base2 = request.host_url
    if base2.startswith("http://"):
        base2 = base2.replace("http://", "https://", 1)
    return urljoin(base2, path.lstrip("/"))

def send_confirmation_email(app, mail, user, token_max_age_seconds: int):
    s = make_serializer(app.config["SECRET_KEY"], app.config["SECURITY_SALT"])
    token = s.dumps({"uid": user.id, "email": user.email})
    link = absolute_url(app.config.get("PUBLIC_BASE_URL", ""), url_for("confirm_email", token=token))

    if not app.config["MAIL_USERNAME"] or not app.config["MAIL_PASSWORD"]:
        app.logger.warning("[MAIL] Missing creds. DEV link: %s", link)
        return {"sent": False, "dev_link": link, "error": "MAIL creds missing"}

    try:
        html = render_template("email_confirm.html", username=user.username, link=link)
        msg = Message(
            subject="Підтвердження email — EarthCity",
            recipients=[user.email],
            html=html,
            sender=app.config["MAIL_DEFAULT_SENDER"]
        )
        mail.send(msg)
        return {"sent": True, "dev_link": None, "error": None}
    except Exception as e:
        app.logger.exception("[MAIL ERROR] %s", repr(e))
        return {"sent": False, "dev_link": link, "error": str(e)}
