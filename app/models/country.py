import json
from datetime import datetime
from ..extensions import db

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
