import os
import logging
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix
from flask import Flask

from .config import Config
from .extensions import db, mail, login_manager, oauth
from .db_init import init_db

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("earthcity")

def create_app():
    load_dotenv()

    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    app.config.from_object(Config)

    db.init_app(app)
    mail.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = None

    # ✅ Google OAuth init + register provider
    oauth.init_app(app)

    if app.config.get("GOOGLE_CLIENT_ID") and app.config.get("GOOGLE_CLIENT_SECRET"):
        oauth.register(
            name="google",
            client_id=app.config["GOOGLE_CLIENT_ID"],
            client_secret=app.config["GOOGLE_CLIENT_SECRET"],
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
    else:
        log.warning("Google OAuth disabled: GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET not set")

    # blueprints
    from .blueprints.pages import bp_pages
    from .blueprints.api_auth import bp_api_auth
    from .blueprints.api_world import bp_api_world
    from .blueprints.api_countries import bp_api_countries
    from .blueprints.api_factories import bp_api_factories
    from .blueprints.admin_api import bp_admin_api

    app.register_blueprint(bp_pages)
    app.register_blueprint(bp_api_auth)
    app.register_blueprint(bp_api_world)
    app.register_blueprint(bp_api_countries)
    app.register_blueprint(bp_api_factories)
    app.register_blueprint(bp_admin_api)

    init_db(app)

    return app
