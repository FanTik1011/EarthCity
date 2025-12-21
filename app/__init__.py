import logging
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv

from .config import Config
from .extensions import db, login_manager, mail
from .models import User
from .services.admin_bootstrap import ensure_admin_from_env

def create_app():
    # Local .env support (Heroku uses Config Vars)
    from pathlib import Path

    # Force-load .env from project root (works on Heroku if .env is committed)
    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(env_path, override=False)


    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.config.from_object(Config)

    # Heroku / reverse proxy
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    # Logging
    logging.basicConfig(level=app.config["LOG_LEVEL"])
    app.logger.setLevel(app.config["LOG_LEVEL"])

    # Extensions
    db.init_app(app)
    mail.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = None

    @login_manager.user_loader
    def load_user(user_id: str):
        try:
            return db.session.get(User, int(user_id))
        except Exception:
            return None

    # Routes
    from .routes.pages import pages_bp
    from .routes.auth import auth_bp
    from .routes.rules import rules_bp
    from .routes.countries import countries_bp
    from .routes.factories import factories_bp
    from .routes.admin import admin_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(rules_bp)
    app.register_blueprint(countries_bp)
    app.register_blueprint(factories_bp)
    app.register_blueprint(admin_bp)

    with app.app_context():
        db.create_all()
        ensure_admin_from_env(User, db, app.logger)

    return app
