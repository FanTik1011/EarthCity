from flask import Flask, render_template
from flask_login import LoginManager, login_required

from config import Config
from models import db
from models.user import User

from routes.auth import auth_bp
from routes.cities import cities_bp


def create_app():
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static"
    )
    app.config.from_object(Config)

    # DB
    db.init_app(app)

    # Login manager
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    @login_manager.user_loader
    def load_user(user_id: str):
        return User.query.get(int(user_id))

    # Main page
    @app.get("/")
    def index():
        return render_template("index.html")

    # ✅ 3D city page (editor)
    @app.get("/city/<int:city_id>")
    @login_required
    def city_3d(city_id: int):
        # нічого не передаємо в шаблон (city_id візьмеш з URL у city3d.js)
        return render_template("city_3d.html")

    # Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(cities_bp)

    # Create tables
    with app.app_context():
        db.create_all()

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
