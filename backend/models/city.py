from datetime import datetime
from . import db

class City(db.Model):
    __tablename__ = "cities"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(32), nullable=False, index=True)

    lat = db.Column(db.Float, nullable=False, index=True)
    lng = db.Column(db.Float, nullable=False, index=True)

    radius_km = db.Column(db.Float, nullable=False, default=15.0)

    mayor_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    tax = db.Column(db.Float, nullable=False, default=5.0)
    rating = db.Column(db.Integer, nullable=False, default=50)
    safety = db.Column(db.String(30), nullable=False, default="Medium")
    players = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
