from flask import Flask, send_from_directory
from flask_cors import CORS
from config import Config
from models import db
from routes import register_blueprints
import os

def create_app():
    app = Flask(__name__, static_folder="static", static_url_path="/")
    app.config.from_object(Config)

    CORS(app)
    db.init_app(app)

    # ✅ якщо ти відмовився від Google/Discord — НЕ підключай OAuth
    # from services.oauth_clients import init_oauth
    # init_oauth(app)

    register_blueprints(app)

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/<path:path>")
    def static_proxy(path: str):
        full_path = os.path.join(app.static_folder, path)
        if os.path.isfile(full_path):
            return send_from_directory(app.static_folder, path)
        return send_from_directory(app.static_folder, "index.html")

    return app

# ✅ важливо: gunicorn буде шукати "app" тут
app = create_app()

# ✅ на Heroku це ок, але краще так (створить БД при старті)
with app.app_context():
    db.create_all()

# Локальний запуск (для тебе на ПК)
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
