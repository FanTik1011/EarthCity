# app/models/country_inventory.py
from datetime import datetime
from ..extensions import db

class CountryInventory(db.Model):
    __tablename__ = "country_inventory"

    id = db.Column(db.Integer, primary_key=True)
    country_id = db.Column(db.Integer, db.ForeignKey("country.id"), nullable=False, index=True)
    resource = db.Column(db.String(32), nullable=False, index=True)
    amount = db.Column(db.Float, nullable=False, default=0.0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("country_id", "resource", name="uq_country_resource"),
    )
