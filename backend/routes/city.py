import math
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from models import db
from models.city import City
from models.user import User

city_bp = Blueprint("city_bp", __name__)

# --------- helpers ----------
def haversine_km(lat1, lng1, lat2, lng2):
    R = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dlng/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def expand_cost(old_radius_km: float, add_km: float) -> int:
    """
    MVP: ціна росте, чим більше місто.
    +1 км біля 15км ~ 10-20к
    """
    new_r = old_radius_km + add_km
    if add_km <= 0:
        return 0
    base = 12000
    scale = 1.0 + (old_radius_km / 20.0)
    # трохи “нелінійно”, щоб не було гігантів одразу
    return int(base * add_km * scale)

def parse_bbox(bbox: str):
    parts = (bbox or "").split(",")
    if len(parts) != 4:
        return None
    w, s, e, n = map(float, parts)
    return w, s, e, n

# --------- API ----------

@city_bp.get("/api/cities")
def list_cities():
    bbox = parse_bbox(request.args.get("bbox", ""))
    if not bbox:
        return jsonify({"cities": []})

    w, s, e, n = bbox
    zoom = int(request.args.get("zoom", "3"))

    # простий ліміт по зуму (чим більший зум, тим більше міст можна віддати)
    limit = 200 if zoom >= 7 else 80

    q = (City.query
         .filter(City.lng >= w, City.lng <= e, City.lat >= s, City.lat <= n)
         .order_by(City.id.desc())
         .limit(limit))

    cities = q.all()
    return jsonify({
        "cities": [{
            "id": c.id,
            "name": c.name,
            "country": c.country,
            "lat": c.lat,
            "lng": c.lng,
            "rating": c.happiness,     # поки мапимо happiness -> rating
            "players": 0,              # MVP (пізніше будемо рахувати)
            "safety": "High" if c.safety >= 75 else ("Medium" if c.safety >= 45 else "Low"),
            "tax": round(c.tax_rate, 1),
            "radius_km": round(c.radius_km, 2),
        } for c in cities]
    })

@city_bp.get("/api/cities/<int:city_id>")
def city_detail(city_id: int):
    c = City.query.get_or_404(city_id)
    return jsonify({
        "id": c.id,
        "name": c.name,
        "country": c.country,
        "lat": c.lat,
        "lng": c.lng,
        "rating": c.happiness,
        "players": 0,
        "safety": "High" if c.safety >= 75 else ("Medium" if c.safety >= 45 else "Low"),
        "tax": round(c.tax_rate, 1),
        "radius_km": round(c.radius_km, 2),
        "budget": c.budget,
        "mayor_user_id": c.mayor_user_id
    })

@city_bp.post("/api/cities/create")
@login_required
def create_city():
    data = request.get_json(force=True, silent=True) or {}

    name = (data.get("name") or "").strip()
    lat = data.get("lat")
    lng = data.get("lng")
    country = (data.get("country") or "").strip() or None

    radius_km = float(data.get("radius_km") or 15.0)
    radius_km = max(5.0, min(radius_km, 50.0))  # MVP ліміт

    if not name:
        return jsonify({"error": "name required"}), 400
    if lat is None or lng is None:
        return jsonify({"error": "lat/lng required"}), 400
    try:
        lat = float(lat); lng = float(lng)
    except:
        return jsonify({"error": "lat/lng invalid"}), 400

    if City.query.filter_by(name=name).first():
        return jsonify({"error": "city name already exists"}), 409

    # анти-хаос: мін. відстань між містами
    min_dist_km = 70.0
    for other in City.query.all():
        d = haversine_km(lat, lng, other.lat, other.lng)
        if d < min_dist_km:
            return jsonify({"error": f"too close to {other.name} ({d:.1f} km). min {min_dist_km:.0f} km"}), 400

    # плата за створення (MVP)
    founding_fee = 60000
    u: User = User.query.get(int(current_user.id))
    if u.balance < founding_fee:
        return jsonify({"error": f"not enough money. need {founding_fee}"}), 400
    u.balance -= founding_fee

    c = City(
        name=name,
        country=country,
        lat=lat,
        lng=lng,
        radius_km=radius_km,
        mayor_user_id=int(current_user.id),
        tax_rate=12.0,
        safety=60,
        happiness=70,
        economy_index=50,
        budget=0
    )

    db.session.add(c)
    db.session.commit()

    return jsonify({"ok": True, "city_id": c.id, "new_balance": u.balance}), 201

@city_bp.post("/api/cities/<int:city_id>/expand")
@login_required
def expand_city(city_id: int):
    c = City.query.get_or_404(city_id)

    if int(current_user.id) != int(c.mayor_user_id):
        return jsonify({"error": "only mayor can expand territory"}), 403

    data = request.get_json(force=True, silent=True) or {}
    add_km = float(data.get("add_km") or 0)
    add_km = max(0.5, min(add_km, 10.0))  # MVP: за раз 0.5..10 км

    old_r = float(c.radius_km)
    if old_r >= 80:
        return jsonify({"error": "max radius reached"}), 400

    cost = expand_cost(old_r, add_km)

    u: User = User.query.get(int(current_user.id))
    if u.balance < cost:
        return jsonify({"error": f"not enough money. need {cost}", "cost": cost}), 400

    u.balance -= cost
    c.radius_km = min(80.0, old_r + add_km)
    c.budget += int(cost * 0.25)  # 25% йде в бюджет міста як “fees” (приємна механіка)

    db.session.commit()

    return jsonify({
        "ok": True,
        "city_id": c.id,
        "new_radius_km": round(c.radius_km, 2),
        "cost": cost,
        "new_balance": u.balance,
        "city_budget": c.budget
    })
