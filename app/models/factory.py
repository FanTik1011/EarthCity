from datetime import datetime
from ..extensions import db

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
