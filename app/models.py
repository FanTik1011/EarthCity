import json
from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from .extensions import db

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    is_confirmed = db.Column(db.Boolean, default=False, nullable=False)
    confirmed_at = db.Column(db.DateTime, nullable=True)

    coins = db.Column(db.Integer, default=5000, nullable=False)
    starter_granted = db.Column(db.Boolean, default=True, nullable=False)

    # Admin
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_blocked = db.Column(db.Boolean, default=False, nullable=False)
    blocked_reason = db.Column(db.String(255), nullable=True)
    blocked_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def set_password(self, raw: str) -> None:
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw: str) -> bool:
        return check_password_hash(self.password_hash, raw)


class Country(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    name = db.Column(db.String(120), nullable=False)
    color = db.Column(db.String(16), nullable=False, default="#7c3aed")
    area_km2 = db.Column(db.Float, nullable=False, default=0.0)
    create_cost = db.Column(db.Integer, nullable=False, default=0)

    geom_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    owner = db.relationship("User", lazy=True)

    def to_feature(self):
        try:
            geom = json.loads(self.geom_json)
        except Exception:
            geom = {"type": "Polygon", "coordinates": []}

        return {
            "type": "Feature",
            "id": self.id,
            "properties": {
                "id": self.id,
                "name": self.name,
                "color": self.color,
                "owner": self.owner.username if self.owner else "unknown",
                "owner_user_id": self.owner_user_id,
                "area_km2": float(self.area_km2 or 0),
                "create_cost": int(self.create_cost or 0),
            },
            "geometry": geom
        }


class Factory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    country_id = db.Column(db.Integer, db.ForeignKey("country.id"), nullable=False)
    owner_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    blueprint = db.Column(db.String(60), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    icon = db.Column(db.String(16), nullable=False, default="🏭")

    lng = db.Column(db.Float, nullable=False)
    lat = db.Column(db.Float, nullable=False)

    level = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    stored_coins = db.Column(db.Integer, default=0, nullable=False)
    last_collected_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    country = db.relationship("Country", lazy=True)

    def to_feature(self):
        return {
            "type": "Feature",
            "properties": {
                "id": self.id,
                "country_id": self.country_id,
                "owner_user_id": self.owner_user_id,
                "blueprint": self.blueprint,
                "name": self.name,
                "icon": self.icon,
                "level": int(self.level or 1),
            },
            "geometry": {"type": "Point", "coordinates": [float(self.lng), float(self.lat)]}
        }
