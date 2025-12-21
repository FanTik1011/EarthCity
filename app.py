# app.py
# EarthCity — env/.env ready (local) + Heroku ready (Config Vars)
# Local:  python app.py
# Heroku: gunicorn app:app

import os
import json
import math
import logging
from datetime import datetime
from urllib.parse import urljoin

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

# NEW: load .env locally (Heroku ignores .env by default)
from dotenv import load_dotenv


# ---------------------------
# Load env
# ---------------------------
load_dotenv()  # reads .env if exists


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

TOKEN_MAX_AGE_SECONDS = int(os.getenv("TOKEN_MAX_AGE_SECONDS", str(60 * 60 * 24)))


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

# If you want to force a specific public base URL (optional)
# Example: https://earthcity-xxxxx.herokuapp.com
app.config["PUBLIC_BASE_URL"] = os.getenv("PUBLIC_BASE_URL", "").strip()


# ---------------------------
# Extensions
# ---------------------------
db = SQLAlchemy(app)
mail = Mail(app)

login_manager = LoginManager(app)
login_manager.login_view = None


# ---------------------------
# GEO helpers
# ---------------------------
def rad(d: float) -> float:
    return d * math.pi / 180.0

def haversine_km(lng1, lat1, lng2, lat2) -> float:
    R = 6371.0088
    dlat = rad(lat2 - lat1)
    dlng = rad(lng2 - lng1)
    a = math.sin(dlat/2)**2 + math.cos(rad(lat1)) * math.cos(rad(lat2)) * math.sin(dlng/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
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


# ---------------------------
# Resources & Blueprints (same as yours, shortened note: keep as-is)
# ---------------------------
RESOURCE_NODES = [
    {"type":"oil", "name":"Oil Basin", "lng":50.5, "lat":24.0, "strength":0.95},
    {"type":"oil", "name":"Oil Field", "lng":44.0, "lat":30.0, "strength":0.78},
    {"type":"oil", "name":"Oil Sands", "lng":-113.5, "lat":56.0, "strength":0.66},
    {"type":"oil", "name":"Offshore Oil", "lng":6.5, "lat":53.2, "strength":0.71},
    {"type":"gas", "name":"Gas Field", "lng":56.0, "lat":25.5, "strength":0.86},
    {"type":"gas", "name":"Gas Field", "lng":36.0, "lat":31.0, "strength":0.72},
    {"type":"gas", "name":"Gas Field", "lng":65.0, "lat":39.0, "strength":0.77},
    {"type":"gas", "name":"Gas Field", "lng":133.0, "lat":-23.0, "strength":0.73},

    {"type":"iron", "name":"Iron Ore", "lng":32.2, "lat":47.8, "strength":0.88},
    {"type":"iron", "name":"Iron Deposit", "lng":107.0, "lat":52.0, "strength":0.67},
    {"type":"iron", "name":"Iron Ore", "lng":-74.0, "lat":5.0, "strength":0.70},
    {"type":"gold", "name":"Gold", "lng":-2.0, "lat":7.0, "strength":0.72},
    {"type":"gold", "name":"Gold", "lng":120.5, "lat":-3.0, "strength":0.60},
    {"type":"rare", "name":"Rare Minerals", "lng":28.0, "lat":-3.0, "strength":0.78},
    {"type":"rare", "name":"Rare Minerals", "lng":103.0, "lat":26.0, "strength":0.70},
    {"type":"uranium", "name":"Uranium", "lng":133.0, "lat":-22.0, "strength":0.72},
    {"type":"coal", "name":"Coal", "lng":24.5, "lat":49.5, "strength":0.82},
    {"type":"coal", "name":"Coal", "lng":88.0, "lat":23.0, "strength":0.70},
    {"type":"coal", "name":"Coal", "lng":147.0, "lat":-33.0, "strength":0.66},

    {"type":"water", "name":"Fresh Water", "lng":90.0, "lat":23.8, "strength":0.90},
    {"type":"water", "name":"Fresh Water", "lng":30.5, "lat":-1.3, "strength":0.76},
    {"type":"water", "name":"Fresh Water", "lng":137.0, "lat":36.0, "strength":0.74},
    {"type":"farmland", "name":"Farmland", "lng":31.2, "lat":49.2, "strength":0.88},
    {"type":"farmland", "name":"Farmland", "lng":10.5, "lat":50.7, "strength":0.74},
    {"type":"farmland", "name":"Farmland", "lng":-58.0, "lat":-34.5, "strength":0.66},
    {"type":"fish", "name":"Fishing Zone", "lng":142.0, "lat":41.5, "strength":0.72},
    {"type":"fish", "name":"Fishing Zone", "lng":16.0, "lat":55.5, "strength":0.68},

    {"type":"wind", "name":"Wind Zone", "lng":8.0, "lat":56.0, "strength":0.75},
    {"type":"wind", "name":"Wind Zone", "lng":145.0, "lat":-35.0, "strength":0.73},
    {"type":"solar", "name":"Solar", "lng":25.0, "lat":23.0, "strength":0.86},
    {"type":"solar", "name":"Solar", "lng":-112.0, "lat":34.0, "strength":0.78},
    {"type":"hydro", "name":"Hydro Potential", "lng":85.0, "lat":28.0, "strength":0.78},
    {"type":"geo", "name":"Geothermal", "lng":-21.9, "lat":64.9, "strength":0.64},
]

FACTORY_BLUEPRINTS = {
    "steel_mill": {"name":"Steel Mill","icon":"🏗️","desc":"Iron+Coal → profit","build_cost":900,"upkeep":0,"base_income_per_hour":70,"requires":{"iron":1,"coal":1}},
    "oil_refinery":{"name":"Oil Refinery","icon":"🛢️","desc":"Oil → money","build_cost":1100,"upkeep":0,"base_income_per_hour":95,"requires":{"oil":1}},
    "gas_plant":{"name":"Gas Plant","icon":"🔥","desc":"Gas → profit","build_cost":980,"upkeep":0,"base_income_per_hour":82,"requires":{"gas":1}},
    "hydro_plant":{"name":"Hydro Plant","icon":"🌊","desc":"Hydro → profit","build_cost":950,"upkeep":0,"base_income_per_hour":78,"requires":{"hydro":1}},
    "farm_complex":{"name":"Farm Complex","icon":"🌾","desc":"Farmland → profit","build_cost":650,"upkeep":0,"base_income_per_hour":52,"requires":{"farmland":1}},
    "waterworks":{"name":"Waterworks","icon":"💧","desc":"Water → profit","build_cost":720,"upkeep":0,"base_income_per_hour":50,"requires":{"water":1}},
    "rare_lab":{"name":"Rare Lab","icon":"💎","desc":"Rare → big profit","build_cost":1400,"upkeep":0,"base_income_per_hour":130,"requires":{"rare":1}},
    "gold_mint":{"name":"Gold Mint","icon":"🪙","desc":"Gold → big profit","build_cost":1350,"upkeep":0,"base_income_per_hour":125,"requires":{"gold":1}},
    "shipyard":{"name":"Shipyard","icon":"⚓","desc":"Fish → profit","build_cost":1000,"upkeep":0,"base_income_per_hour":88,"requires":{"fish":1}},
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
# Email tokens + URL helpers
# ---------------------------
def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key=app.config["SECRET_KEY"], salt=app.config["SECURITY_SALT"])

def make_confirm_token(user: User) -> str:
    return _serializer().dumps({"uid": user.id, "email": user.email})

def parse_confirm_token(token: str):
    return _serializer().loads(token, max_age=TOKEN_MAX_AGE_SECONDS)

def absolute_url(path: str) -> str:
    # If user provided PUBLIC_BASE_URL, use it (best for stable hosting)
    base = (app.config.get("PUBLIC_BASE_URL") or "").rstrip("/")
    if base:
        return urljoin(base + "/", path.lstrip("/"))

    # Otherwise compute from request (ProxyFix helps on Heroku)
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
        return jsonify(authenticated=False, username=None, email=None, is_confirmed=False, coins=0, has_country=False)

    has_country = Country.query.filter_by(owner_user_id=current_user.id).first() is not None
    return jsonify(
        authenticated=True,
        username=current_user.username,
        email=current_user.email,
        is_confirmed=bool(current_user.is_confirmed),
        coins=int(current_user.coins or 0),
        has_country=bool(has_country)
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
        coins=START_COINS
    )
    db.session.add(user)
    db.session.commit()

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

    login_user(user)

    has_country = Country.query.filter_by(owner_user_id=user.id).first() is not None
    return jsonify(ok=True, is_confirmed=bool(user.is_confirmed), username=user.username, coins=int(user.coins or 0), has_country=bool(has_country))

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

    return render_template("confirm_result.html", ok=True, msg="Email підтверджено ✅ Повернись на вкладку з глобусом і зроби Login (або перезавантаж сторінку).")


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
        "factory_max_per_country": FACTORY_MAX_PER_COUNTRY
    })

@app.get("/api/resources")
def api_resources():
    fc = {"type": "FeatureCollection", "features": []}
    for idx, n in enumerate(RESOURCE_NODES, start=1):
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
    return jsonify(ok=True, data=fc)

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

@app.post("/api/countries")
def api_countries_create():
    if not current_user.is_authenticated:
        return jsonify(ok=False, error="Not authenticated"), 401
    if not current_user.is_confirmed:
        return jsonify(ok=False, error="Email not confirmed"), 403

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
        geom_json=json.dumps(geom, ensure_ascii=False)
    )
    db.session.add(country)
    db.session.commit()

    return jsonify(ok=True, country=country.to_feature(), coins=int(current_user.coins or 0))


# ---------------------------
# Factories API (same logic as yours)
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
    near = []
    for n in RESOURCE_NODES:
        if not point_in_polygon(n["lng"], n["lat"], ring):
            continue
        if haversine_km(lng, lat, n["lng"], n["lat"]) <= FACTORY_PICK_RADIUS_KM:
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


# ---------------------------
# Init DB once per dyno boot
# ---------------------------
with app.app_context():
    db.create_all()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=(os.getenv("FLASK_DEBUG", "0") == "1"))
