# app.py
# EarthCity — Globe + Auth + MMO Countries + Resources + Factories
# Run local: python app.py
# Heroku: gunicorn app:app

import os
import json
import math
from datetime import datetime
from urllib.parse import urljoin

from flask import Flask, render_template, request, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin,
    login_required, login_user, logout_user, current_user
)
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix


# ---------------------------
# Game economy constants
# ---------------------------
START_COINS = 5000

COUNTRY_BASE_COST = 800
COUNTRY_COST_PER_1000_KM2 = 35
COUNTRY_MAX_AREA_KM2 = 250_000
COUNTRY_MAX_POINTS = 60
COUNTRY_MIN_POINTS = 3

FACTORY_PLACE_FEE = 120
FACTORY_MAX_PER_COUNTRY = 40
FACTORY_ACCUM_CAP_HOURS = 72
FACTORY_PICK_RADIUS_KM = 120

TOKEN_MAX_AGE_SECONDS = 60 * 60 * 24  # 24h


# ---------------------------
# App + Config
# ---------------------------
app = Flask(__name__)

# Heroku sits behind proxy -> correct scheme/host for url_for/external links
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev_change_me")
app.config["SECURITY_SALT"] = os.getenv("SECURITY_SALT", "dev_salt_change_me")

# Heroku Postgres provides DATABASE_URL=postgres://... (SQLAlchemy expects postgresql://)
db_url = os.getenv("DATABASE_URL", "sqlite:///app.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Better cookie behavior in production
is_prod = os.getenv("FLASK_ENV") == "production" or os.getenv("HEROKU_APP_NAME") is not None
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_HTTPONLY"] = True
if is_prod:
    # on https deployments
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["PREFERRED_URL_SCHEME"] = "https"
else:
    app.config["PREFERRED_URL_SCHEME"] = "http"

# Gmail SMTP (use App Password)
app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "smtp.gmail.com")
app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", "587"))
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USE_SSL"] = False
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME", "")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD", "")
app.config["MAIL_DEFAULT_SENDER"] = os.getenv(
    "MAIL_DEFAULT_SENDER",
    app.config["MAIL_USERNAME"] or "no-reply@example.com"
)


# ---------------------------
# Extensions
# ---------------------------
db = SQLAlchemy(app)
mail = Mail(app)

login_manager = LoginManager(app)
login_manager.login_view = None


# ---------------------------
# Helpers: geo / math
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
    n = len(ring) - 1  # ignore duplicate last
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
# Resources & Blueprints
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

    {"type":"iron", "name":"Iron Deposit", "lng":27.0, "lat":62.0, "strength":0.75},
    {"type":"oil", "name":"Oil Field", "lng":115.0, "lat":4.5, "strength":0.69},
    {"type":"gas", "name":"Gas Field", "lng":-2.0, "lat":54.5, "strength":0.68},
    {"type":"rare", "name":"Rare Minerals", "lng":-70.0, "lat":-20.0, "strength":0.66},
    {"type":"water", "name":"Fresh Water", "lng":105.0, "lat":12.0, "strength":0.70},
    {"type":"wind", "name":"Wind Zone", "lng":-102.0, "lat":49.0, "strength":0.66},
    {"type":"fish", "name":"Fishing Zone", "lng":-76.0, "lat":36.5, "strength":0.70},
    {"type":"solar", "name":"Solar", "lng":55.0, "lat":-23.0, "strength":0.74},
]

FACTORY_BLUEPRINTS = {
    "steel_mill": {"name":"Steel Mill","icon":"🏗️","desc":"Переробляє Iron+Coal в стабільний прибуток.","build_cost":900,"upkeep":0,"base_income_per_hour":70,"requires":{"iron":1,"coal":1}},
    "oil_refinery": {"name":"Oil Refinery","icon":"🛢️","desc":"Нафта → гроші. Потребує Oil поряд.","build_cost":1100,"upkeep":0,"base_income_per_hour":95,"requires":{"oil":1}},
    "gas_plant": {"name":"Gas Plant","icon":"🔥","desc":"Газова енергетика. Стабільний дохід.","build_cost":980,"upkeep":0,"base_income_per_hour":82,"requires":{"gas":1}},
    "hydro_plant": {"name":"Hydro Plant","icon":"🌊","desc":"Потребує Hydro Potential поруч.","build_cost":950,"upkeep":0,"base_income_per_hour":78,"requires":{"hydro":1}},
    "farm_complex": {"name":"Farm Complex","icon":"🌾","desc":"Потребує Farmland.","build_cost":650,"upkeep":0,"base_income_per_hour":52,"requires":{"farmland":1}},
    "waterworks": {"name":"Waterworks","icon":"💧","desc":"Потребує Water поруч.","build_cost":720,"upkeep":0,"base_income_per_hour":50,"requires":{"water":1}},
    "rare_lab": {"name":"Rare Lab","icon":"💎","desc":"Потребує Rare Minerals.","build_cost":1400,"upkeep":0,"base_income_per_hour":130,"requires":{"rare":1}},
    "gold_mint": {"name":"Gold Mint","icon":"🪙","desc":"Потребує Gold поруч.","build_cost":1350,"upkeep":0,"base_income_per_hour":125,"requires":{"gold":1}},
    "shipyard": {"name":"Shipyard","icon":"⚓","desc":"Потребує Fish.","build_cost":1000,"upkeep":0,"base_income_per_hour":88,"requires":{"fish":1}},
}


# ---------------------------
# DB models
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
# Tokens / mail helpers
# ---------------------------
def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        secret_key=app.config["SECRET_KEY"],
        salt=app.config["SECURITY_SALT"]
    )

def make_confirm_token(user: User) -> str:
    return _serializer().dumps({"uid": user.id, "email": user.email})

def parse_confirm_token(token: str):
    return _serializer().loads(token, max_age=TOKEN_MAX_AGE_SECONDS)

def absolute_url(path: str) -> str:
    # request.url_root respects ProxyFix -> correct https on Heroku
    return urljoin(request.url_root, path.lstrip("/"))

def send_confirmation_email(user: User) -> dict:
    token = make_confirm_token(user)
    link = absolute_url(url_for("confirm_email", token=token))

    # Dev fallback
    if not app.config["MAIL_USERNAME"] or not app.config["MAIL_PASSWORD"]:
        print("\n[DEV] Confirmation link:", link, "\n")
        return {"sent": False, "dev_link": link}

    try:
        html = render_template("email_confirm.html", username=user.username, link=link)
        msg = Message(
            subject="Підтвердження email — EarthCity",
            recipients=[user.email],
            html=html
        )
        mail.send(msg)
        return {"sent": True, "dev_link": None}
    except Exception as e:
        # Don't crash registration if mail fails
        print("\n[MAIL ERROR]", repr(e))
        print("[DEV] Confirmation link:", link, "\n")
        return {"sent": False, "dev_link": link}


# ---------------------------
# Pages
# ---------------------------
@app.get("/")
def globe_page():
    return render_template("globe_auth.html")


# ---------------------------
# API: session & auth
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
    return jsonify(ok=True, sent=result["sent"], dev_link=result["dev_link"])


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
        return jsonify(ok=True, already=True, sent=True, dev_link=None)

    result = send_confirmation_email(current_user)
    return jsonify(ok=True, sent=result["sent"], dev_link=result["dev_link"])


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
# Rules + Resources + Blueprints
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
# Countries API (MMO)
# ---------------------------
@app.get("/api/countries")
def api_countries_list():
    countries = Country.query.order_by(Country.created_at.asc()).all()
    fc = {"type": "FeatureCollection", "features": [c.to_feature() for c in countries]}
    return jsonify(ok=True, data=fc)


def _validate_polygon(geom: dict) -> tuple[bool, str]:
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

    already = Country.query.filter_by(owner_user_id=current_user.id).first()
    if already:
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


@app.get("/api/countries/<int:cid>")
def api_country_details(cid: int):
    c = db.session.get(Country, cid)
    if not c:
        return jsonify(ok=False, error="Country not found"), 404

    me_id = current_user.id if current_user.is_authenticated else None
    is_mine = bool(me_id and c.owner_user_id == me_id)

    owner = db.session.get(User, c.owner_user_id)
    owner_username = owner.username if owner else "Unknown"

    f_count = Factory.query.filter_by(country_id=c.id).count()

    return jsonify(ok=True, data={
        "id": c.id,
        "name": c.name,
        "color": c.color,
        "area_km2": float(c.area_km2 or 0),
        "owner_user_id": c.owner_user_id,
        "owner_username": owner_username,
        "is_mine": is_mine,
        "factories": int(f_count),
    })


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


@app.post("/api/factories")
@login_required
def api_factory_build():
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
# Optional: preview email template
# ---------------------------
@app.get("/__email_preview")
def email_preview():
    return render_template("email_confirm.html", username="Volodya", link="https://example.com/confirm/xxx")


# ---------------------------
# Start
# ---------------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=not is_prod)
