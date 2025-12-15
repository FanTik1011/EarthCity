from datetime import datetime
from flask_login import UserMixin
from . import db

class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(db.String(40), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=True, index=True)  # може бути null для OAuth-only
    password_hash = db.Column(db.String(255), nullable=True)

    role = db.Column(db.String(32), nullable=False, default="worker")  # worker/entrepreneur/politician/...
    balance = db.Column(db.Integer, nullable=False, default=1000)
    reputation = db.Column(db.Integer, nullable=False, default=0)

    home_city_id = db.Column(db.Integer, db.ForeignKey("cities.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
