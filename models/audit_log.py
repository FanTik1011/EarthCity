from datetime import datetime
from . import db

class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)

    entity_type = db.Column(db.String(40), nullable=False)   # "city"
    entity_id = db.Column(db.Integer, nullable=False)

    action = db.Column(db.String(60), nullable=False)        # "tax_changed"
    payload_json = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
