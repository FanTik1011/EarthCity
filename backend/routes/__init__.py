from .auth import auth_bp, login_manager
from .map import map_bp
from .city_rules import city_rules_bp

def register_blueprints(app):
    app.register_blueprint(auth_bp)
    app.register_blueprint(map_bp)
    app.register_blueprint(city_rules_bp)

    login_manager.init_app(app)
