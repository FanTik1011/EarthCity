from datetime import datetime
from . import db

class Event(db.Model):
    __tablename__ = "events"

    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(60), nullable=False, index=True)

    city_id = db.Column(db.Integer, db.ForeignKey("cities.id"), nullable=True, index=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)

    payload_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
