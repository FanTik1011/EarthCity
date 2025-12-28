# app/models/market_offer.py
from datetime import datetime
from ..extensions import db

class MarketOffer(db.Model):
    __tablename__ = "market_offer"

    id = db.Column(db.Integer, primary_key=True)

    seller_country_id = db.Column(db.Integer, db.ForeignKey("country.id"), nullable=False, index=True)
    resource = db.Column(db.String(32), nullable=False, index=True)

    price_per_unit = db.Column(db.Integer, nullable=False)  # EC per 1 unit
    amount_total = db.Column(db.Float, nullable=False)
    amount_left = db.Column(db.Float, nullable=False)

    is_active = db.Column(db.Boolean, nullable=False, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "seller_country_id": self.seller_country_id,
            "resource": self.resource,
            "price_per_unit": int(self.price_per_unit),
            "amount_total": float(self.amount_total),
            "amount_left": float(self.amount_left),
            "is_active": bool(self.is_active),
            "created_at": self.created_at.isoformat() + "Z",
        }
