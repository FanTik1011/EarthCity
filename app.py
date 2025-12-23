# app.py
# EarthCity — env/.env ready (local) + Heroku ready (Config Vars)
# Local:  python app.py
# Heroku: gunicorn app:app

import os
import json
import math
import logging
import random
from datetime import datetime
from urllib.parse import urljoin
from functools import wraps

from flask import Flask, render_template, request, url_for, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin,
    login_required, login_user, logout_user, current_user
)
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from sqlalchemy import text as sa_text

# NEW: load .env locally (Heroku ignores .env by default)
from dotenv import load_dotenv

# ---------------------------
# Load env
# ---------------------------
load_dotenv()  # reads .env if exists

# ---------------------------
# HARD-CODE ADMIN (email only)
# ---------------------------
HARDCODE_ADMIN_EMAILS = {
    "volodakotlarov191@gmail.com",
}

# ---------------------------
# Logging
# ---------------------------
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("earthcity")

# ---------------------------
# Economy constants
# ---------------------------
START_COINS = int(os.getenv("START_COINS", "5000"))

COUNTRY_BASE_COST = int(os.getenv("COUNTRY_BASE_COST", "800"))
COUNTRY_COST_PER_1000_KM2 = int(os.getenv("COUNTRY_COST_PER_1000_KM2", "35"))
COUNTRY_MAX_AREA_KM2 = int(os.getenv("COUNTRY_MAX_AREA_KM2", "250000"))
COUNTRY_MAX_POINTS = int(os.getenv("COUNTRY_MAX_POINTS", "60"))
COUNTRY_MIN_POINTS = int(os.getenv("COUNTRY_MIN_POINTS", "3"))

FACTORY_PLACE_FEE = int(os.getenv("FACTORY_PLACE_FEE", "120"))
FACTORY_MAX_PER_COUNTRY = int(os.getenv("FACTORY_MAX_PER_COUNTRY", "40"))
FACTORY_ACCUM_CAP_HOURS = int(os.getenv("FACTORY_ACCUM_CAP_HOURS", "72"))
FACTORY_PICK_RADIUS_KM = int(os.getenv("FACTORY_PICK_RADIUS_KM", "120"))

# NEW: expand territory economy
EXPAND_BASE_FEE = int(os.getenv("EXPAND_BASE_FEE", "250"))
EXPAND_COST_PER_1000_KM2 = int(os.getenv("EXPAND_COST_PER_1000_KM2", "55"))
EXPAND_MAX_DELTA_KM2 = float(os.getenv("EXPAND_MAX_DELTA_KM2", "180000"))  # max extra in one expansion

TOKEN_MAX_AGE_SECONDS = int(os.getenv("TOKEN_MAX_AGE_SECONDS", str(60 * 60 * 24)))

# ---------------------------
# Resources generation (server)
# ---------------------------
# NOTE: you asked about RESOURCE_TOTAL_TARGET and RESOURCE_MIN_DIST_KM
# Put ONE value in .env:
#   RESOURCE_TOTAL_TARGET=900
#   RESOURCE_MIN_DIST_KM=45
RESOURCE_TOTAL_TARGET = int(os.getenv("RESOURCE_TOTAL_TARGET", "250"))
RESOURCE_MIN_DIST_KM = float(os.getenv("RESOURCE_MIN_DIST_KM", "70"))
RESOURCE_SEED = int(os.getenv("RESOURCE_SEED", "20251223"))

def _normalize_db_url(raw: str) -> str:
    if not raw:
        return "sqlite:///app.db"
    if raw.startswith("postgres://"):
        return raw.replace("postgres://", "postgresql://", 1)
    return raw

# ---------------------------
# App config
# ---------------------------
app = Flask(__name__)

# If behind proxy (Heroku), this fixes https + host
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev_change_me")
app.config["SECURITY_SALT"] = os.getenv("SECURITY_SALT", "dev_salt_change_me")

app.config["SQLALCHEMY_DATABASE_URI"] = _normalize_db_url(os.getenv("DATABASE_URL", "sqlite:///app.db"))
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Generate external links with https (important for confirm links on Heroku)
app.config["PREFERRED_URL_SCHEME"] = os.getenv("PREFERRED_URL_SCHEME", "https")

# Cookies (good for https hosting)
app.config["SESSION_COOKIE_SAMESITE"] = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "1") == "1"

# Mail (Gmail)
app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "smtp.gmail.com")
app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", "587"))
app.config["MAIL_USE_TLS"] = os.getenv("MAIL_USE_TLS", "1") == "1"
app.config["MAIL_USE_SSL"] = os.getenv("MAIL_USE_SSL", "0") == "1"
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME", "")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD", "")
app.config["MAIL_DEFAULT_SENDER"] = os.getenv(
    "MAIL_DEFAULT_SENDER",
    app.config["MAIL_USERNAME"] or "no-reply@example.com"
)

# Optional: force a specific public base URL
app.config["PUBLIC_BASE_URL"] = os.getenv("PUBLIC_BASE_URL", "").strip()

# ---------------------------
# Extensions
# ---------------------------
db = SQLAlchemy(app)
mail = Mail(app)

login_manager = LoginManager(app)
login_manager.login_view = None

def auto_promote_admin(user):
    """
    Make user admin automatically if their email is in HARDCODE_ADMIN_EMAILS.
    Safe: affects only your email(s).
    """
    try:
        if not user or not getattr(user, "email", None):
            return
        if user.email.strip().lower() in HARDCODE_ADMIN_EMAILS and not getattr(user, "is_admin", False):
            user.is_admin = True
            db.session.commit()
    except Exception:
        db.session.rollback()

# ---------------------------
# GEO helpers
# ---------------------------
def rad(d: float) -> float:
    return d * math.pi / 180.0

def haversine_km(lng1, lat1, lng2, lat2) -> float:
    R = 6371.0088
    dlat = rad(lat2 - lat1)
    dlng = rad(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rad(lat1)) * math.cos(rad(lat2)) * math.sin(dlng / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def point_in_polygon(lng: float, lat: float, ring) -> bool:
    if not ring or len(ring) < 4:
        return False
    inside = False
    n = len(ring) - 1
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        intersect = ((yi > lat) != (yj > lat)) and (lng < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi)
        if intersect:
            inside = not inside
        j = i
    return inside

def polygon_area_km2_equirect(geom: dict) -> float:
    R = 6371.0088
    ring = geom["coordinates"][0]
    pts = ring[:-1]
    if len(pts) < 3:
        return 0.0

    lat0 = sum(p[1] for p in pts) / len(pts)
    lat0r = rad(lat0)

    xy = []
    for lng, lat in pts:
        x = R * rad(lng) * math.cos(lat0r)
        y = R * rad(lat)
        xy.append((x, y))

    s = 0.0
    for i in range(len(xy)):
        x1, y1 = xy[i]
        x2, y2 = xy[(i + 1) % len(xy)]
        s += x1 * y2 - x2 * y1

    return abs(s) / 2.0

def compute_country_cost(area_km2: float) -> int:
    return int(round(COUNTRY_BASE_COST + (area_km2 / 1000.0) * COUNTRY_COST_PER_1000_KM2))

def compute_expand_cost(delta_area_km2: float) -> int:
    delta_area_km2 = max(0.0, float(delta_area_km2))
    return int(round(EXPAND_BASE_FEE + (delta_area_km2 / 1000.0) * EXPAND_COST_PER_1000_KM2))

# ---------------------------
# Resources & Blueprints
# ---------------------------
# Base nodes (hand-made) kept as before
RESOURCE_NODES = [
    {"type": "oil", "name": "Oil Basin", "lng": 50.5, "lat": 24.0, "strength": 0.95},
    {"type": "oil", "name": "Oil Field", "lng": 44.0, "lat": 30.0, "strength": 0.78},
    {"type": "oil", "name": "Oil Sands", "lng": -113.5, "lat": 56.0, "strength": 0.66},
    {"type": "oil", "name": "Offshore Oil", "lng": 6.5, "lat": 53.2, "strength": 0.71},
    {"type": "gas", "name": "Gas Field", "lng": 56.0, "lat": 25.5, "strength": 0.86},
    {"type": "gas", "name": "Gas Field", "lng": 36.0, "lat": 31.0, "strength": 0.72},
    {"type": "gas", "name": "Gas Field", "lng": 65.0, "lat": 39.0, "strength": 0.77},
    {"type": "gas", "name": "Gas Field", "lng": 133.0, "lat": -23.0, "strength": 0.73},

    {"type": "iron", "name": "Iron Ore", "lng": 32.2, "lat": 47.8, "strength": 0.88},
    {"type": "iron", "name": "Iron Deposit", "lng": 107.0, "lat": 52.0, "strength": 0.67},
    {"type": "iron", "name": "Iron Ore", "lng": -74.0, "lat": 5.0, "strength": 0.70},
    {"type": "gold", "name": "Gold", "lng": -2.0, "lat": 7.0, "strength": 0.72},
    {"type": "gold", "name": "Gold", "lng": 120.5, "lat": -3.0, "strength": 0.60},
    {"type": "rare", "name": "Rare Minerals", "lng": 28.0, "lat": -3.0, "strength": 0.78},
    {"type": "rare", "name": "Rare Minerals", "lng": 103.0, "lat": 26.0, "strength": 0.70},
    {"type": "uranium", "name": "Uranium", "lng": 133.0, "lat": -22.0, "strength": 0.72},
    {"type": "coal", "name": "Coal", "lng": 24.5, "lat": 49.5, "strength": 0.82},
    {"type": "coal", "name": "Coal", "lng": 88.0, "lat": 23.0, "strength": 0.70},
    {"type": "coal", "name": "Coal", "lng": 147.0, "lat": -33.0, "strength": 0.66},

    {"type": "water", "name": "Fresh Water", "lng": 90.0, "lat": 23.8, "strength": 0.90},
    {"type": "water", "name": "Fresh Water", "lng": 30.5, "lat": -1.3, "strength": 0.76},
    {"type": "water", "name": "Fresh Water", "lng": 137.0, "lat": 36.0, "strength": 0.74},
    {"type": "farmland", "name": "Farmland", "lng": 31.2, "lat": 49.2, "strength": 0.88},
    {"type": "farmland", "name": "Farmland", "lng": 10.5, "lat": 50.7, "strength": 0.74},
    {"type": "farmland", "name": "Farmland", "lng": -58.0, "lat": -34.5, "strength": 0.66},
    {"type": "fish", "name": "Fishing Zone", "lng": 142.0, "lat": 41.5, "strength": 0.72},
    {"type": "fish", "name": "Fishing Zone", "lng": 16.0, "lat": 55.5, "strength": 0.68},

    {"type": "wind", "name": "Wind Zone", "lng": 8.0, "lat": 56.0, "strength": 0.75},
    {"type": "wind", "name": "Wind Zone", "lng": 145.0, "lat": -35.0, "strength": 0.73},
    {"type": "solar", "name": "Solar", "lng": 25.0, "lat": 23.0, "strength": 0.86},
    {"type": "solar", "name": "Solar", "lng": -112.0, "lat": 34.0, "strength": 0.78},
    {"type": "hydro", "name": "Hydro Potential", "lng": 85.0, "lat": 28.0, "strength": 0.78},
    {"type": "geo", "name": "Geothermal", "lng": -21.9, "lat": 64.9, "strength": 0.64},
]

FACTORY_BLUEPRINTS = {
    "steel_mill": {"name": "Steel Mill", "icon": "🏗️", "desc": "Iron+Coal → profit", "build_cost": 900, "upkeep": 0, "base_income_per_hour": 70, "requires": {"iron": 1, "coal": 1}},
    "oil_refinery": {"name": "Oil Refinery", "icon": "🛢️", "desc": "Oil → money", "build_cost": 1100, "upkeep": 0, "base_income_per_hour": 95, "requires": {"oil": 1}},
    "gas_plant": {"name": "Gas Plant", "icon": "🔥", "desc": "Gas → profit", "build_cost": 980, "upkeep": 0, "base_income_per_hour": 82, "requires": {"gas": 1}},
    "hydro_plant": {"name": "Hydro Plant", "icon": "🌊", "desc": "Hydro → profit", "build_cost": 950, "upkeep": 0, "base_income_per_hour": 78, "requires": {"hydro": 1}},
    "farm_complex": {"name": "Farm Complex", "icon": "🌾", "desc": "Farmland → profit", "build_cost": 650, "upkeep": 0, "base_income_per_hour": 52, "requires": {"farmland": 1}},
    "waterworks": {"name": "Waterworks", "icon": "💧", "desc": "Water → profit", "build_cost": 720, "upkeep": 0, "base_income_per_hour": 50, "requires": {"water": 1}},
    "rare_lab": {"name": "Rare Lab", "icon": "💎", "desc": "Rare → big profit", "build_cost": 1400, "upkeep": 0, "base_income_per_hour": 130, "requires": {"rare": 1}},
    "gold_mint": {"name": "Gold Mint", "icon": "🪙", "desc": "Gold → big profit", "build_cost": 1350, "upkeep": 0, "base_income_per_hour": 125, "requires": {"gold": 1}},
    "shipyard": {"name": "Shipyard", "icon": "⚓", "desc": "Fish → profit", "build_cost": 1000, "upkeep": 0, "base_income_per_hour": 88, "requires": {"fish": 1}},
}

# ---------------------------
# Models
# ---------------------------
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_confirmed = db.Column(db.Boolean, default=False, nullable=False)
    confirmed_at = db.Column(db.DateTime, nullable=True)
    coins = db.Column(db.Integer, default=START_COINS, nullable=False)

    # starter bonus lock
    starter_granted = db.Column(db.Boolean, default=True, nullable=False)

    # Admin / Block
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_blocked = db.Column(db.Boolean, default=False, nullable=False)
    blocked_reason = db.Column(db.String(255), nullable=True)
    blocked_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

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

    # NEW: track last expansion
    expanded_at = db.Column(db.DateTime, nullable=True)
    expansions_count = db.Column(db.Integer, default=0, nullable=False)

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
                "expansions_count": int(self.expansions_count or 0),
            },
            "geometry": geom
        }

class Factory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    country_id = db.Column(db.Integer, db.ForeignKey("country.id"), nullable=False)
    owner_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    blueprint = db.Column(db.String(60), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    icon = db.Column(db.String(16), nullable=False, default="🏭")

    lng = db.Column(db.Float, nullable=False)
    lat = db.Column(db.Float, nullable=False)

    level = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    stored_coins = db.Column(db.Integer, default=0, nullable=False)
    last_collected_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    country = db.relationship("Country", lazy=True)

    def to_feature(self):
        return {
            "type": "Feature",
            "properties": {
                "id": self.id,
                "country_id": self.country_id,
                "owner_user_id": self.owner_user_id,
                "blueprint": self.blueprint,
                "name": self.name,
                "icon": self.icon,
                "level": int(self.level or 1),
            },
            "geometry": {"type": "Point", "coordinates": [float(self.lng), float(self.lat)]}
        }

@login_manager.user_loader
def load_user(user_id: str):
    try:
        return db.session.get(User, int(user_id))
    except Exception:
        return None

# ---------------------------
# Admin helpers
# ---------------------------
def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify(ok=False, error="Not authenticated"), 401
        if getattr(current_user, "is_blocked", False):
            logout_user()
            return jsonify(ok=False, error="Blocked"), 403
        if not getattr(current_user, "is_admin", False):
            return jsonify(ok=False, error="Admin only"), 403
        return fn(*args, **kwargs)
    return wrapper

@app.before_request
def _kick_blocked_users():
    if current_user.is_authenticated and getattr(current_user, "is_blocked", False):
        logout_user()
        if request.path.startswith("/api/") or request.path.startswith("/admin/api/"):
            return jsonify(ok=False, error="Blocked"), 403

# ---------------------------
# Email tokens + URL helpers
# ---------------------------
def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key=app.config["SECRET_KEY"], salt=app.config["SECURITY_SALT"])

def make_confirm_token(user: User) -> str:
    return _serializer().dumps({"uid": user.id, "email": user.email})

def parse_confirm_token(token: str):
    return _serializer().loads(token, max_age=TOKEN_MAX_AGE_SECONDS)

def absolute_url(path: str) -> str:
    base = (app.config.get("PUBLIC_BASE_URL") or "").rstrip("/")
    if base:
        return urljoin(base + "/", path.lstrip("/"))

    base2 = request.host_url
    if base2.startswith("http://"):
        base2 = base2.replace("http://", "https://", 1)
    return urljoin(base2, path.lstrip("/"))

def send_confirmation_email(user: User) -> dict:
    token = make_confirm_token(user)
    link = absolute_url(url_for("confirm_email", token=token))

    if not app.config["MAIL_USERNAME"] or not app.config["MAIL_PASSWORD"]:
        log.warning("[MAIL] Missing creds. DEV link: %s", link)
        return {"sent": False, "dev_link": link, "error": "MAIL creds missing"}

    try:
        html = render_template("email_confirm.html", username=user.username, link=link)
        msg = Message(
            subject="Підтвердження email — EarthCity",
            recipients=[user.email],
            html=html,
            sender=app.config["MAIL_DEFAULT_SENDER"]
        )
        mail.send(msg)
        return {"sent": True, "dev_link": None, "error": None}
    except Exception as e:
        log.exception("[MAIL ERROR] %s", repr(e))
        return {"sent": False, "dev_link": link, "error": str(e)}

# ---------------------------
# Pages
# ---------------------------
@app.get("/")
def globe_page():
    return render_template("globe_auth.html")

@app.get("/admin")
@login_required
def admin_page():
    if not getattr(current_user, "is_admin", False):
        return ("Forbidden", 403)
    return render_template("admin_panel.html")

@app.get("/favicon.ico")
def favicon():
    static_path = os.path.join(app.root_path, "static")
    if os.path.exists(os.path.join(static_path, "favicon.ico")):
        return send_from_directory(static_path, "favicon.ico")
    return ("", 204)

# ---------------------------
# API: auth/session
# ---------------------------
@app.get("/api/me")
def api_me():
    if not current_user.is_authenticated:
        return jsonify(
            authenticated=False,
            username=None,
            email=None,
            is_confirmed=False,
            coins=0,
            has_country=False,
            starter_granted=False,
            is_admin=False,
            is_blocked=False
        )

    has_country = Country.query.filter_by(owner_user_id=current_user.id).first() is not None
    return jsonify(
        authenticated=True,
        username=current_user.username,
        email=current_user.email,
        is_confirmed=bool(current_user.is_confirmed),
        coins=int(current_user.coins or 0),
        has_country=bool(has_country),
        starter_granted=bool(getattr(current_user, "starter_granted", True)),
        is_admin=bool(getattr(current_user, "is_admin", False)),
        is_blocked=bool(getattr(current_user, "is_blocked", False))
    )

@app.post("/api/register")
def api_register():
    data = request.get_json(force=True, silent=True) or {}

    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if len(username) < 3:
        return jsonify(ok=False, error="Username мінімум 3 символи."), 400
    if "@" not in email or "." not in email:
        return jsonify(ok=False, error="Некоректний email."), 400
    if len(password) < 6:
        return jsonify(ok=False, error="Пароль мінімум 6 символів."), 400

    if User.query.filter_by(username=username).first():
        return jsonify(ok=False, error="Такий username вже існує."), 409
    if User.query.filter_by(email=email).first():
        return jsonify(ok=False, error="Такий email вже зареєстрований."), 409

    user = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(password),
        is_confirmed=False,
        confirmed_at=None,
        coins=START_COINS,
        starter_granted=True
    )
    db.session.add(user)
    db.session.commit()

    auto_promote_admin(user)
    login_user(user)

    result = send_confirmation_email(user)
    return jsonify(ok=True, sent=result["sent"], dev_link=result["dev_link"], mail_error=result["error"])

@app.post("/api/login")
def api_login():
    data = request.get_json(force=True, silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify(ok=False, error="Невірний email або пароль."), 401

    if getattr(user, "is_blocked", False):
        return jsonify(ok=False, error="Акаунт заблоковано адміністратором."), 403

    login_user(user)
    auto_promote_admin(user)

    has_country = Country.query.filter_by(owner_user_id=user.id).first() is not None
    return jsonify(
        ok=True,
        is_confirmed=bool(user.is_confirmed),
        username=user.username,
        coins=int(user.coins or 0),
        has_country=bool(has_country),
        starter_granted=bool(getattr(user, "starter_granted", True)),
        is_admin=bool(getattr(user, "is_admin", False)),
        is_blocked=bool(getattr(user, "is_blocked", False))
    )

@app.post("/api/logout")
def api_logout():
    if current_user.is_authenticated:
        logout_user()
    return jsonify(ok=True)

@app.post("/api/resend-confirmation")
def api_resend_confirmation():
    if not current_user.is_authenticated:
        return jsonify(ok=False, error="Not authenticated"), 401
    if current_user.is_confirmed:
        return jsonify(ok=True, already=True, sent=True, dev_link=None, mail_error=None)

    result = send_confirmation_email(current_user)
    return jsonify(ok=True, sent=result["sent"], dev_link=result["dev_link"], mail_error=result["error"])

@app.get("/confirm/<token>")
def confirm_email(token: str):
    try:
        data = parse_confirm_token(token)
    except SignatureExpired:
        return render_template("confirm_result.html", ok=False, msg="Токен прострочений. Натисни Resend на сторінці.")
    except BadSignature:
        return render_template("confirm_result.html", ok=False, msg="Невірний токен.")

    user = db.session.get(User, int(data.get("uid", 0)))
    if not user or user.email != data.get("email"):
        return render_template("confirm_result.html", ok=False, msg="Користувача не знайдено або email не співпадає.")

    if not user.is_confirmed:
        user.is_confirmed = True
        user.confirmed_at = datetime.utcnow()
        db.session.commit()

    return render_template(
        "confirm_result.html",
        ok=True,
        msg="Email підтверджено ✅ Повернись на вкладку з глобусом і зроби Login (або перезавантаж сторінку)."
    )

# ---------------------------
# Admin API
# ---------------------------
@app.get("/admin/api/users")
@admin_required
def admin_api_users():
    users = User.query.order_by(User.created_at.desc()).all()
    out = []
    for u in users:
        out.append({
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "coins": int(u.coins or 0),
            "is_confirmed": bool(u.is_confirmed),
            "is_admin": bool(getattr(u, "is_admin", False)),
            "is_blocked": bool(getattr(u, "is_blocked", False)),
            "blocked_reason": u.blocked_reason,
            "blocked_at": u.blocked_at.isoformat() if u.blocked_at else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        })
    return jsonify(ok=True, data=out)

@app.post("/admin/api/users/<int:uid>/block")
@admin_required
def admin_api_block(uid: int):
    data = request.get_json(force=True, silent=True) or {}
    reason = (data.get("reason") or "Blocked by admin").strip()[:255]

    u = db.session.get(User, uid)
    if not u:
        return jsonify(ok=False, error="User not found"), 404
    if u.id == current_user.id:
        return jsonify(ok=False, error="You cannot block yourself"), 400
    if getattr(u, "is_admin", False):
        return jsonify(ok=False, error="You cannot block another admin"), 400

    u.is_blocked = True
    u.blocked_reason = reason
    u.blocked_at = datetime.utcnow()
    db.session.commit()
    return jsonify(ok=True)

@app.post("/admin/api/users/<int:uid>/unblock")
@admin_required
def admin_api_unblock(uid: int):
    u = db.session.get(User, uid)
    if not u:
        return jsonify(ok=False, error="User not found"), 404

    u.is_blocked = False
    u.blocked_reason = None
    u.blocked_at = None
    db.session.commit()
    return jsonify(ok=True)

@app.post("/admin/api/users/<int:uid>/give_coins")
@admin_required
def admin_api_give_coins(uid: int):
    data = request.get_json(force=True, silent=True) or {}
    amount = int(data.get("amount") or 0)

    if amount == 0:
        return jsonify(ok=False, error="amount required"), 400
    if amount < -1_000_000 or amount > 1_000_000:
        return jsonify(ok=False, error="amount too large"), 400

    u = db.session.get(User, uid)
    if not u:
        return jsonify(ok=False, error="User not found"), 404

    new_balance = int(u.coins or 0) + amount
    if new_balance < 0:
        new_balance = 0
    u.coins = new_balance
    db.session.commit()
    return jsonify(ok=True, coins=int(u.coins or 0))

# ---------------------------
# Rules + resources + blueprints
# ---------------------------
@app.get("/api/rules")
def api_rules():
    return jsonify(ok=True, rules={
        "start_coins": START_COINS,
        "country_base_cost": COUNTRY_BASE_COST,
        "country_cost_per_1000_km2": COUNTRY_COST_PER_1000_KM2,
        "country_max_area_km2": COUNTRY_MAX_AREA_KM2,
        "country_max_points": COUNTRY_MAX_POINTS,
        "factory_place_fee": FACTORY_PLACE_FEE,
        "factory_pick_radius_km": FACTORY_PICK_RADIUS_KM,
        "factory_max_per_country": FACTORY_MAX_PER_COUNTRY,
        # expand rules
        "expand_base_fee": EXPAND_BASE_FEE,
        "expand_cost_per_1000_km2": EXPAND_COST_PER_1000_KM2,
        "expand_max_delta_km2": EXPAND_MAX_DELTA_KM2,
    })

# ---------------------------
# LAND (GeoJSON) + polygon intersection helpers
# ---------------------------
LAND_GEOJSON_PATH = os.path.join(app.root_path, "static", "data", "land.geojson")
LAND_FEATURES = None  # cached parsed land polygons

def _load_land_geojson():
    global LAND_FEATURES
    if LAND_FEATURES is not None:
        return LAND_FEATURES

    if not os.path.exists(LAND_GEOJSON_PATH):
        log.warning("land.geojson not found at %s (sea check disabled)", LAND_GEOJSON_PATH)
        LAND_FEATURES = []
        return LAND_FEATURES

    try:
        with open(LAND_GEOJSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        LAND_FEATURES = data.get("features") or []
        log.info("Loaded land.geojson features: %d", len(LAND_FEATURES))
        return LAND_FEATURES
    except Exception as e:
        log.warning("Failed to load land.geojson (%s). Sea check disabled.", e)
        LAND_FEATURES = []
        return LAND_FEATURES

def _rings_from_geom(geom: dict):
    if not geom or not isinstance(geom, dict):
        return []
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    rings = []
    if gtype == "Polygon":
        if isinstance(coords, list) and coords and isinstance(coords[0], list):
            ring = coords[0]
            if isinstance(ring, list) and len(ring) >= 4:
                rings.append(ring)
    elif gtype == "MultiPolygon":
        if isinstance(coords, list):
            for poly in coords:
                if not poly or not isinstance(poly, list):
                    continue
                ring = poly[0] if poly and isinstance(poly[0], list) else None
                if isinstance(ring, list) and len(ring) >= 4:
                    rings.append(ring)
    return rings

def _point_on_land(lng: float, lat: float) -> bool:
    feats = _load_land_geojson()
    if not feats:
        return True  # allow if file missing
    for feat in feats:
        g = (feat or {}).get("geometry") or {}
        for ring in _rings_from_geom(g):
            if point_in_polygon(lng, lat, ring):
                return True
    return False

def _polygon_is_on_land(geom: dict) -> bool:
    ring = (geom.get("coordinates") or [[]])[0]
    pts = ring[:-1]
    if not pts:
        return False
    for lng, lat in pts:
        if not _point_on_land(float(lng), float(lat)):
            return False
    return True

# ---- polygon intersection (country-on-country) ----
def _orient(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])

def _on_segment(a, b, c):
    return (min(a[0], b[0]) <= c[0] <= max(a[0], b[0]) and
            min(a[1], b[1]) <= c[1] <= max(a[1], b[1]))

def _segments_intersect(p1, p2, q1, q2) -> bool:
    o1 = _orient(p1, p2, q1)
    o2 = _orient(p1, p2, q2)
    o3 = _orient(q1, q2, p1)
    o4 = _orient(q1, q2, p2)

    if (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0):
        return True

    eps = 1e-12
    if abs(o1) < eps and _on_segment(p1, p2, q1): return True
    if abs(o2) < eps and _on_segment(p1, p2, q2): return True
    if abs(o3) < eps and _on_segment(q1, q2, p1): return True
    if abs(o4) < eps and _on_segment(q1, q2, p2): return True

    return False

def _rings_intersect(ringA, ringB) -> bool:
    if not ringA or not ringB:
        return False

    A = ringA[:-1]
    B = ringB[:-1]
    if len(A) < 3 or len(B) < 3:
        return False

    for i in range(len(A)):
        p1 = A[i]
        p2 = A[(i + 1) % len(A)]
        for j in range(len(B)):
            q1 = B[j]
            q2 = B[(j + 1) % len(B)]
            if _segments_intersect(p1, p2, q1, q2):
                return True

    if point_in_polygon(B[0][0], B[0][1], ringA):
        return True
    if point_in_polygon(A[0][0], A[0][1], ringB):
        return True

    return False

def _geom_intersects_any_country(new_geom: dict, exclude_country_id: int | None = None) -> bool:
    new_ring = (new_geom.get("coordinates") or [[]])[0]
    if not new_ring:
        return False

    for c in Country.query.all():
        if exclude_country_id and c.id == exclude_country_id:
            continue
        try:
            old_geom = json.loads(c.geom_json)
            old_ring = (old_geom.get("coordinates") or [[]])[0]
        except Exception:
            continue
        if _rings_intersect(new_ring, old_ring):
            return True

    return False

def _validate_polygon(geom: dict):
    if not isinstance(geom, dict):
        return False, "Geometry must be object"
    if geom.get("type") != "Polygon":
        return False, "Only Polygon supported"
    coords = geom.get("coordinates")
    if not isinstance(coords, list) or len(coords) < 1:
        return False, "Polygon coordinates invalid"
    ring = coords[0]
    if not isinstance(ring, list) or len(ring) < (COUNTRY_MIN_POINTS + 1):
        return False, f"Polygon ring must have {COUNTRY_MIN_POINTS+1}+ points"
    if len(ring) > (COUNTRY_MAX_POINTS + 1):
        return False, f"Too many points (max {COUNTRY_MAX_POINTS})"
    for p in ring:
        if (not isinstance(p, list)) or len(p) != 2:
            return False, "Point must be [lng, lat]"
        lng, lat = p
        if not (isinstance(lng, (int, float)) and isinstance(lat, (int, float))):
            return False, "lng/lat must be numbers"
        if lng < -180 or lng > 180 or lat < -90 or lat > 90:
            return False, "lng/lat out of range"
    if ring[0] != ring[-1]:
        return False, "Polygon ring must be closed (first==last)"
    return True, ""

def _country_ring(country: Country):
    try:
        geom = json.loads(country.geom_json)
        return geom["coordinates"][0]
    except Exception:
        return None

def _new_polygon_contains_old(old_ring, new_ring) -> bool:
    """
    Simple rule for expansion:
    new polygon must contain ALL vertices of old polygon (outer ring).
    """
    if not old_ring or not new_ring:
        return False
    old_pts = old_ring[:-1]
    if not old_pts:
        return False
    for lng, lat in old_pts:
        if not point_in_polygon(float(lng), float(lat), new_ring):
            return False
    return True

# ---------------------------
# Resource generation + LOD serving
# ---------------------------
_RESOURCE_CACHE = None  # list of dict nodes

_RESOURCE_TYPES = [
    "oil", "gas", "iron", "gold", "coal", "uranium", "rare",
    "water", "farmland", "fish", "wind", "solar", "hydro", "geo"
]

def _resource_name_for(t: str) -> str:
    names = {
        "oil": "Oil Field",
        "gas": "Gas Field",
        "iron": "Iron Ore",
        "gold": "Gold",
        "coal": "Coal",
        "uranium": "Uranium",
        "rare": "Rare Minerals",
        "water": "Fresh Water",
        "farmland": "Farmland",
        "fish": "Fishing Zone",
        "wind": "Wind Zone",
        "solar": "Solar Zone",
        "hydro": "Hydro Potential",
        "geo": "Geothermal",
    }
    return names.get(t, t)

def _deg_bucket(lng: float, lat: float, cell_deg: float):
    return (int((lng + 180.0) / cell_deg), int((lat + 90.0) / cell_deg))

def _generate_resources_if_needed():
    """
    Generates extra resources to reach RESOURCE_TOTAL_TARGET.
    Fast-ish + cached.
    Uses land.geojson if present to keep them on land, otherwise allow everywhere.
    """
    global _RESOURCE_CACHE
    if _RESOURCE_CACHE is not None:
        return _RESOURCE_CACHE

    feats = _load_land_geojson()  # may be []
    rng = random.Random(RESOURCE_SEED)

    nodes = list(RESOURCE_NODES)  # keep base nodes

    target = max(len(nodes), int(RESOURCE_TOTAL_TARGET))
    min_dist = max(5.0, float(RESOURCE_MIN_DIST_KM))

    # grid acceleration for min-distance check
    # 1 degree ~ 111km -> choose cell about min_dist/111
    cell_deg = max(0.25, min_dist / 111.0)
    grid = {}  # (gx,gy)-> list of (lng,lat)

    def can_place(lng, lat) -> bool:
        if feats:
            if not _point_on_land(lng, lat):
                return False
        gx, gy = _deg_bucket(lng, lat, cell_deg)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                pts = grid.get((gx + dx, gy + dy)) or []
                for (plng, plat) in pts:
                    if haversine_km(lng, lat, plng, plat) < min_dist:
                        return False
        return True

    def add_to_grid(lng, lat):
        gx, gy = _deg_bucket(lng, lat, cell_deg)
        grid.setdefault((gx, gy), []).append((lng, lat))

    # seed grid with existing
    for n in nodes:
        add_to_grid(float(n["lng"]), float(n["lat"]))

    # generate
    attempts = 0
    max_attempts = target * 200  # avoid infinite loops
    while len(nodes) < target and attempts < max_attempts:
        attempts += 1

        # bias to habitable latitudes a bit (less at poles)
        lat = rng.uniform(-58, 75)
        lng = rng.uniform(-179.9, 179.9)

        if not can_place(lng, lat):
            continue

        t = rng.choice(_RESOURCE_TYPES)
        strength = round(rng.uniform(0.55, 0.98), 2)

        nodes.append({
            "type": t,
            "name": _resource_name_for(t),
            "lng": float(lng),
            "lat": float(lat),
            "strength": float(strength),
        })
        add_to_grid(lng, lat)

    if len(nodes) < target:
        log.warning("Resource generation reached %d/%d (min_dist too strict or land mask too small).", len(nodes), target)
    else:
        log.info("Resource generation done: %d nodes (target %d), min_dist %.1fkm", len(nodes), target, min_dist)

    _RESOURCE_CACHE = nodes
    return _RESOURCE_CACHE

def _resources_to_featurecollection(nodes):
    fc = {"type": "FeatureCollection", "features": []}
    for idx, n in enumerate(nodes, start=1):
        fc["features"].append({
            "type": "Feature",
            "id": idx,
            "properties": {
                "type": n["type"],
                "name": n.get("name") or n["type"],
                "strength": float(n.get("strength", 0.5))
            },
            "geometry": {"type": "Point", "coordinates": [float(n["lng"]), float(n["lat"])]}
        })
    return fc

def _parse_bbox(bbox_str: str):
    try:
        parts = [float(x) for x in bbox_str.split(",")]
        if len(parts) != 4:
            return None
        west, south, east, north = parts
        west = max(-180.0, min(180.0, west))
        east = max(-180.0, min(180.0, east))
        south = max(-90.0, min(90.0, south))
        north = max(-90.0, min(90.0, north))
        return west, south, east, north
    except Exception:
        return None

def _in_bbox(lng, lat, bbox):
    west, south, east, north = bbox
    # handle antimeridian bbox (west > east)
    if west <= east:
        return (west <= lng <= east) and (south <= lat <= north)
    return ((lng >= west) or (lng <= east)) and (south <= lat <= north)

def _lod_downsample(features, zoom: float, limit: int):
    """
    Grid-based "best per cell" to reduce points.
    Keeps stronger nodes.
    """
    if limit <= 0 or len(features) <= limit:
        return features

    # choose grid cell degrees depending on zoom
    # high zoom => smaller cells => more points allowed naturally
    # tweak if you want: smaller => more points
    cell_deg = 18.0 / max(1.0, (2.0 ** max(0.0, min(6.0, float(zoom)))))
    cell_deg = max(0.20, min(6.0, cell_deg))

    best = {}
    for f in features:
        lng, lat = f["geometry"]["coordinates"]
        gx, gy = _deg_bucket(float(lng), float(lat), cell_deg)
        key = (gx, gy)
        s = float((f.get("properties") or {}).get("strength", 0.5))
        cur = best.get(key)
        if not cur:
            best[key] = (s, f)
        else:
            if s > cur[0]:
                best[key] = (s, f)

    out = [v[1] for v in best.values()]

    # still too many => take top by strength
    if len(out) > limit:
        out.sort(key=lambda f: float((f.get("properties") or {}).get("strength", 0.5)), reverse=True)
        out = out[:limit]

    return out

@app.get("/api/resources")
def api_resources():
    """
    Supports old call (no params) and LOD call:
      /api/resources?bbox=west,south,east,north&zoom=3.2&limit=2000
    """
    nodes = _generate_resources_if_needed()
    fc = _resources_to_featurecollection(nodes)

    bbox_str = request.args.get("bbox", "").strip()
    zoom_str = request.args.get("zoom", "").strip()
    limit_str = request.args.get("limit", "").strip()

    if not bbox_str:
        # old behavior: return all (but if huge, still clip a bit for safety)
        # keep it consistent: if too huge, return a reasonable LOD
        feats = fc["features"]
        if len(feats) > 6000:
            feats2 = _lod_downsample(feats, zoom=1.0, limit=6000)
            fc2 = {"type": "FeatureCollection", "features": feats2}
            return jsonify(ok=True, data=fc2)
        return jsonify(ok=True, data=fc)

    bbox = _parse_bbox(bbox_str)
    if not bbox:
        return jsonify(ok=False, error="Invalid bbox"), 400

    try:
        zoom = float(zoom_str) if zoom_str else 1.0
    except Exception:
        zoom = 1.0

    try:
        limit = int(limit_str) if limit_str else 2000
    except Exception:
        limit = 2000

    limit = max(50, min(12000, limit))

    # filter to bbox
    feats = []
    for f in fc["features"]:
        lng, lat = f["geometry"]["coordinates"]
        if _in_bbox(float(lng), float(lat), bbox):
            feats.append(f)

    feats = _lod_downsample(feats, zoom=zoom, limit=limit)
    return jsonify(ok=True, data={"type": "FeatureCollection", "features": feats})

@app.get("/api/blueprints")
def api_blueprints():
    items = []
    for key, bp in FACTORY_BLUEPRINTS.items():
        items.append({
            "key": key,
            "name": bp["name"],
            "icon": bp.get("icon", "🏭"),
            "desc": bp.get("desc", ""),
            "build_cost": int(bp.get("build_cost", 0)),
            "base_income_per_hour": int(bp.get("base_income_per_hour", 0)),
            "requires": bp.get("requires", {})
        })
    return jsonify(ok=True, data=items)

# ---------------------------
# Countries API
# ---------------------------
@app.get("/api/countries")
def api_countries_list():
    countries = Country.query.order_by(Country.created_at.asc()).all()
    fc = {"type": "FeatureCollection", "features": [c.to_feature() for c in countries]}
    return jsonify(ok=True, data=fc)

@app.post("/api/countries")
def api_countries_create():
    if not current_user.is_authenticated:
        return jsonify(ok=False, error="Not authenticated"), 401
    if not current_user.is_confirmed:
        return jsonify(ok=False, error="Email not confirmed"), 403
    if getattr(current_user, "is_blocked", False):
        return jsonify(ok=False, error="Blocked"), 403

    if Country.query.filter_by(owner_user_id=current_user.id).first():
        return jsonify(ok=False, error="Ти вже маєш країну. 1 акаунт = 1 країна."), 409

    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    color = (data.get("color") or "#7c3aed").strip()
    geom = data.get("geometry")

    if len(name) < 2:
        return jsonify(ok=False, error="Name мінімум 2 символи."), 400
    if not color.startswith("#") or len(color) not in (4, 7):
        return jsonify(ok=False, error="Invalid color."), 400

    ok, err = _validate_polygon(geom)
    if not ok:
        return jsonify(ok=False, error=err), 400

    # LAND CHECK
    if not _polygon_is_on_land(geom):
        return jsonify(ok=False, error="Країну можна створювати лише на суші (не на морі/океані)."), 400

    # OVERLAP CHECK
    if _geom_intersects_any_country(geom):
        return jsonify(ok=False, error="Не можна створювати країну на країні (перетин з іншою країною)."), 400

    area_km2 = polygon_area_km2_equirect(geom)
    if area_km2 > COUNTRY_MAX_AREA_KM2:
        return jsonify(ok=False, error=f"Країна занадто велика: {int(area_km2):,} км² (макс {COUNTRY_MAX_AREA_KM2:,} км²)"), 400

    cost = compute_country_cost(area_km2)
    if int(current_user.coins or 0) < cost:
        return jsonify(ok=False, error=f"Недостатньо монет. Треба {cost} EC, у тебе {int(current_user.coins or 0)} EC."), 400

    current_user.coins = int(current_user.coins or 0) - cost

    country = Country(
        owner_user_id=current_user.id,
        name=name[:120],
        color=color,
        area_km2=float(area_km2),
        create_cost=int(cost),
        geom_json=json.dumps(geom, ensure_ascii=False),
        expansions_count=0,
        expanded_at=None,
    )
    db.session.add(country)
    db.session.commit()

    return jsonify(ok=True, country=country.to_feature(), coins=int(current_user.coins or 0))

@app.get("/api/countries/<int:cid>")
def api_country_details(cid: int):
    c = db.session.get(Country, cid)
    if not c:
        return jsonify(ok=False, error="Country not found"), 404

    factories_count = Factory.query.filter_by(country_id=c.id).count()

    is_mine = False
    if current_user.is_authenticated:
        is_mine = (c.owner_user_id == current_user.id)

    return jsonify(ok=True, data={
        "id": c.id,
        "name": c.name,
        "color": c.color,
        "area_km2": float(c.area_km2 or 0),
        "factories": int(factories_count),
        "owner_username": (c.owner.username if c.owner else "unknown"),
        "is_mine": bool(is_mine),
        "expansions_count": int(c.expansions_count or 0),
        "expanded_at": c.expanded_at.isoformat() if c.expanded_at else None,
    })

# ---------------------------
# NEW: Country expansion API
# ---------------------------
@app.post("/api/countries/<int:cid>/expand")
@login_required
def api_country_expand(cid: int):
    if getattr(current_user, "is_blocked", False):
        return jsonify(ok=False, error="Blocked"), 403
    if not current_user.is_confirmed:
        return jsonify(ok=False, error="Email not confirmed"), 403

    country = db.session.get(Country, cid)
    if not country:
        return jsonify(ok=False, error="Country not found"), 404
    if country.owner_user_id != current_user.id:
        return jsonify(ok=False, error="Not your country"), 403

    data = request.get_json(force=True, silent=True) or {}
    geom = data.get("geometry")
    if not geom:
        return jsonify(ok=False, error="geometry required"), 400

    ok, err = _validate_polygon(geom)
    if not ok:
        return jsonify(ok=False, error=err), 400

    # must be on land
    if not _polygon_is_on_land(geom):
        return jsonify(ok=False, error="Розширення можливе лише на суші (не море/океан)."), 400

    # must not intersect other countries (excluding itself)
    if _geom_intersects_any_country(geom, exclude_country_id=country.id):
        return jsonify(ok=False, error="Розширення перетинає іншу країну (заборонено)."), 400

    old_ring = _country_ring(country)
    new_ring = (geom.get("coordinates") or [[]])[0]

    if not old_ring or not new_ring:
        return jsonify(ok=False, error="Invalid country geometry"), 400

    # new must contain old (simple safe rule)
    if not _new_polygon_contains_old(old_ring, new_ring):
        return jsonify(ok=False, error="Нове розширення має повністю накривати стару країну (щоб не «перерізати» її)."), 400

    old_geom = json.loads(country.geom_json)
    old_area = float(country.area_km2 or polygon_area_km2_equirect(old_geom))
    new_area = float(polygon_area_km2_equirect(geom))

    if new_area <= old_area + 1.0:
        return jsonify(ok=False, error="Розширення не збільшує площу."), 400

    if new_area > COUNTRY_MAX_AREA_KM2:
        return jsonify(ok=False, error=f"Завелика країна після розширення (макс {COUNTRY_MAX_AREA_KM2:,} км²)."), 400

    delta = new_area - old_area
    if delta > EXPAND_MAX_DELTA_KM2:
        return jsonify(ok=False, error=f"Занадто велике розширення за раз (макс +{int(EXPAND_MAX_DELTA_KM2):,} км²)."), 400

    cost = compute_expand_cost(delta)
    if int(current_user.coins or 0) < cost:
        return jsonify(ok=False, error=f"Недостатньо монет. Треба {cost} EC."), 400

    current_user.coins = int(current_user.coins or 0) - cost

    country.geom_json = json.dumps(geom, ensure_ascii=False)
    country.area_km2 = float(new_area)
    country.expanded_at = datetime.utcnow()
    country.expansions_count = int(country.expansions_count or 0) + 1

    db.session.commit()
    return jsonify(ok=True, coins=int(current_user.coins or 0), country=country.to_feature(), expand_cost=int(cost), delta_area_km2=float(delta))

# ---------------------------
# Factories API
# ---------------------------
def _country_polygon_ring(country: Country):
    try:
        geom = json.loads(country.geom_json)
        return geom["coordinates"][0]
    except Exception:
        return None

def _resources_near_point_in_country(country: Country, lng: float, lat: float):
    ring = _country_polygon_ring(country)
    if not ring:
        return []

    nodes = _generate_resources_if_needed()

    near = []
    for n in nodes:
        if not point_in_polygon(float(n["lng"]), float(n["lat"]), ring):
            continue
        if haversine_km(lng, lat, float(n["lng"]), float(n["lat"])) <= FACTORY_PICK_RADIUS_KM:
            near.append(n)
    return near

def _calc_factory_rate_per_hour(factory: Factory) -> float:
    bp = FACTORY_BLUEPRINTS.get(factory.blueprint)
    if not bp:
        return 0.0

    base = float(bp.get("base_income_per_hour", 0))
    level = int(factory.level or 1)

    country = db.session.get(Country, factory.country_id)
    if not country:
        return 0.0

    near = _resources_near_point_in_country(country, factory.lng, factory.lat)
    req = bp.get("requires", {})

    strengths = []
    for rtype in req.keys():
        best = None
        for n in near:
            if n["type"] == rtype:
                best = max(best or 0.0, float(n.get("strength", 0.5)))
        if best is not None:
            strengths.append(best)

    eff = (sum(strengths) / len(strengths)) if strengths else 0.0
    mult = 0.75 + 0.65 * eff
    lvl_mult = 1.0 + (max(0, level - 1) * 0.22)
    return base * mult * lvl_mult

def _accrue_factory(factory: Factory, now: datetime):
    last = factory.last_collected_at or now
    dt_hours = (now - last).total_seconds() / 3600.0
    if dt_hours <= 0:
        return

    dt_hours = min(dt_hours, FACTORY_ACCUM_CAP_HOURS)

    rate = _calc_factory_rate_per_hour(factory)
    gain = int(math.floor(rate * dt_hours))
    if gain > 0:
        factory.stored_coins = int(factory.stored_coins or 0) + gain
    factory.last_collected_at = now

@app.get("/api/factories")
def api_factories_list():
    items = Factory.query.order_by(Factory.created_at.asc()).all()
    fc = {"type": "FeatureCollection", "features": [f.to_feature() for f in items]}
    return jsonify(ok=True, data=fc)

@app.get("/api/my/factories")
@login_required
def api_my_factories():
    if getattr(current_user, "is_blocked", False):
        return jsonify(ok=False, error="Blocked"), 403

    now = datetime.utcnow()
    items = Factory.query.filter_by(owner_user_id=current_user.id).all()
    out = []
    for f in items:
        _accrue_factory(f, now)
        out.append({
            "id": f.id,
            "country_id": f.country_id,
            "blueprint": f.blueprint,
            "name": f.name,
            "icon": f.icon,
            "level": int(f.level or 1),
            "lng": float(f.lng),
            "lat": float(f.lat),
            "stored_coins": int(f.stored_coins or 0),
            "rate_per_hour": float(_calc_factory_rate_per_hour(f)),
        })
    db.session.commit()
    return jsonify(ok=True, data=out, coins=int(current_user.coins or 0))

@app.post("/api/factories")
@login_required
def api_factory_build():
    if getattr(current_user, "is_blocked", False):
        return jsonify(ok=False, error="Blocked"), 403
    if not current_user.is_confirmed:
        return jsonify(ok=False, error="Email not confirmed"), 403

    data = request.get_json(force=True, silent=True) or {}
    cid = int(data.get("country_id") or 0)
    blueprint = (data.get("blueprint") or "").strip()
    lng = data.get("lng")
    lat = data.get("lat")

    if cid <= 0:
        return jsonify(ok=False, error="country_id required"), 400
    if blueprint not in FACTORY_BLUEPRINTS:
        return jsonify(ok=False, error="Unknown blueprint"), 400
    if not isinstance(lng, (int, float)) or not isinstance(lat, (int, float)):
        return jsonify(ok=False, error="lng/lat required"), 400
    if lng < -180 or lng > 180 or lat < -90 or lat > 90:
        return jsonify(ok=False, error="lng/lat out of range"), 400

    country = db.session.get(Country, cid)
    if not country:
        return jsonify(ok=False, error="Country not found"), 404
    if country.owner_user_id != current_user.id:
        return jsonify(ok=False, error="Not your country"), 403

    cnt = Factory.query.filter_by(country_id=country.id).count()
    if cnt >= FACTORY_MAX_PER_COUNTRY:
        return jsonify(ok=False, error=f"Factory limit reached (max {FACTORY_MAX_PER_COUNTRY})"), 400

    ring = _country_polygon_ring(country)
    if not ring or not point_in_polygon(float(lng), float(lat), ring):
        return jsonify(ok=False, error="Точку треба ставити ВСЕРЕДИНІ своєї країни."), 400

    bp = FACTORY_BLUEPRINTS[blueprint]
    total_cost = int(bp["build_cost"]) + int(FACTORY_PLACE_FEE)

    if int(current_user.coins or 0) < total_cost:
        return jsonify(ok=False, error=f"Недостатньо монет. Треба {total_cost} EC."), 400

    near = _resources_near_point_in_country(country, float(lng), float(lat))
    req = bp.get("requires", {})
    missing = []

    for rtype, need_count in req.items():
        found = 0
        for n in near:
            if n["type"] == rtype:
                found += 1
        if found < int(need_count):
            missing.append(rtype)

    if missing:
        return jsonify(ok=False, error=f"Нема потрібних ресурсів поруч: {', '.join(missing)} (радіус {FACTORY_PICK_RADIUS_KM} км)."), 400

    current_user.coins = int(current_user.coins or 0) - total_cost

    f = Factory(
        country_id=country.id,
        owner_user_id=current_user.id,
        blueprint=blueprint,
        name=bp["name"],
        icon=bp.get("icon", "🏭"),
        lng=float(lng),
        lat=float(lat),
        level=1,
        stored_coins=0,
        last_collected_at=datetime.utcnow()
    )
    db.session.add(f)
    db.session.commit()

    return jsonify(ok=True, factory=f.to_feature(), coins=int(current_user.coins or 0))

@app.post("/api/factories/<int:fid>/collect")
@login_required
def api_factory_collect(fid: int):
    if getattr(current_user, "is_blocked", False):
        return jsonify(ok=False, error="Blocked"), 403

    f = db.session.get(Factory, fid)
    if not f:
        return jsonify(ok=False, error="Factory not found"), 404
    if f.owner_user_id != current_user.id:
        return jsonify(ok=False, error="Not yours"), 403

    now = datetime.utcnow()
    _accrue_factory(f, now)

    amount = int(f.stored_coins or 0)
    if amount <= 0:
        db.session.commit()
        return jsonify(ok=True, collected=0, coins=int(current_user.coins or 0))

    f.stored_coins = 0
    current_user.coins = int(current_user.coins or 0) + amount
    db.session.commit()

    return jsonify(ok=True, collected=amount, coins=int(current_user.coins or 0))

@app.post("/api/factories/<int:fid>/upgrade")
@login_required
def api_factory_upgrade(fid: int):
    if getattr(current_user, "is_blocked", False):
        return jsonify(ok=False, error="Blocked"), 403

    f = db.session.get(Factory, fid)
    if not f:
        return jsonify(ok=False, error="Factory not found"), 404
    if f.owner_user_id != current_user.id:
        return jsonify(ok=False, error="Not yours"), 403

    now = datetime.utcnow()
    _accrue_factory(f, now)

    next_lvl = int(f.level or 1) + 1
    cost = int(260 * (next_lvl ** 1.55))

    if int(current_user.coins or 0) < cost:
        return jsonify(ok=False, error=f"Not enough coins. Need {cost} EC."), 400

    current_user.coins = int(current_user.coins or 0) - cost
    f.level = next_lvl
    db.session.commit()

    return jsonify(ok=True, level=int(f.level), coins=int(current_user.coins or 0))

# ---------------------------
# Tiny schema ensure for SQLite
# ---------------------------
def _ensure_user_columns_sqlite():
    """
    SQLite only: add new columns if DB already existed.
    Safe ALTER TABLE with checks.
    """
    try:
        cols = [r[1] for r in db.session.execute(sa_text("PRAGMA table_info(user)")).fetchall()]
        alters = []
        if "is_admin" not in cols:
            alters.append("ALTER TABLE user ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0")
        if "is_blocked" not in cols:
            alters.append("ALTER TABLE user ADD COLUMN is_blocked BOOLEAN NOT NULL DEFAULT 0")
        if "blocked_reason" not in cols:
            alters.append("ALTER TABLE user ADD COLUMN blocked_reason VARCHAR(255)")
        if "blocked_at" not in cols:
            alters.append("ALTER TABLE user ADD COLUMN blocked_at DATETIME")

        for sql in alters:
            db.session.execute(sa_text(sql))
        if alters:
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        log.warning("DB migrate (sqlite) skipped/failed: %s", e)

def _ensure_country_columns_sqlite():
    try:
        cols = [r[1] for r in db.session.execute(sa_text("PRAGMA table_info(country)")).fetchall()]
        alters = []
        if "expanded_at" not in cols:
            alters.append("ALTER TABLE country ADD COLUMN expanded_at DATETIME")
        if "expansions_count" not in cols:
            alters.append("ALTER TABLE country ADD COLUMN expansions_count INTEGER NOT NULL DEFAULT 0")

        for sql in alters:
            db.session.execute(sa_text(sql))
        if alters:
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        log.warning("DB migrate (country sqlite) skipped/failed: %s", e)

def _ensure_schema():
    uri = (app.config.get("SQLALCHEMY_DATABASE_URI") or "")
    if uri.startswith("sqlite"):
        _ensure_user_columns_sqlite()
        _ensure_country_columns_sqlite()

# ---------------------------
# Init DB once per dyno boot
# ---------------------------
with app.app_context():
    db.create_all()
    _ensure_schema()
    # warm up land + resources cache (optional but helps first request)
    try:
        _load_land_geojson()
    except Exception:
        pass
    try:
        _generate_resources_if_needed()
    except Exception as e:
        log.warning("Resources warm-up failed: %s", e)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=(os.getenv("FLASK_DEBUG", "0") == "1"))
