from datetime import datetime
from . import db

class OAuthAccount(db.Model):
    __tablename__ = "oauth_accounts"

    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(20), nullable=False, index=True)     # "google" / "discord"
    provider_user_id = db.Column(db.String(128), nullable=False, index=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("provider", "provider_user_id", name="uq_provider_user"),
    )
