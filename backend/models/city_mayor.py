from datetime import datetime
from . import db

class CityMayor(db.Model):
    __tablename__ = "city_mayors"

    city_id = db.Column(db.Integer, db.ForeignKey("cities.id"), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    elected_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
