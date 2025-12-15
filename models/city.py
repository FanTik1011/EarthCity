from datetime import datetime
from . import db

class City(db.Model):
    __tablename__ = "cities"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    country = db.Column(db.String(120), nullable=False, index=True)
    lat = db.Column(db.Float, nullable=False, index=True)
    lng = db.Column(db.Float, nullable=False, index=True)

    rating = db.Column(db.Integer, nullable=False, default=50)
    players_count = db.Column(db.Integer, nullable=False, default=0)
    safety_level = db.Column(db.String(32), nullable=False, default="Medium")

    tax_percent = db.Column(db.Integer, nullable=False, default=10)  # базове, але мер міняє через rules
    budget = db.Column(db.Integer, nullable=False, default=0)

    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_marker_json(self):
        return {
            "id": self.id,
            "name": self.name,
            "country": self.country,
            "lat": self.lat,
            "lng": self.lng,
            "rating": self.rating,
            "players": self.players_count,
            "safety": self.safety_level,
            "tax": self.tax_percent,
        }
