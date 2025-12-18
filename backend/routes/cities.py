import json
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from models import db
from models.city import City
from models.audit_log import AuditLog

cities_bp = Blueprint("cities_bp", __name__)

def _audit(entity_type: str, entity_id: int, action: str, payload: dict | None = None):
    db.session.add(AuditLog(
        actor_user_id=(current_user.id if current_user.is_authenticated else None),
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        payload_json=json.dumps(payload or {}, ensure_ascii=False)
    ))

@cities_bp.get("/api/cities")
def list_cities():
    bbox = (request.args.get("bbox") or "").strip()
    try:
        west, south, east, north = [float(x) for x in bbox.split(",")]
    except Exception:
        return jsonify({"error": "bbox required: west,south,east,north"}), 400

    q = City.query.filter(
        City.lng >= west, City.lng <= east,
        City.lat >= south, City.lat <= north
    ).limit(2000)

    cities = [{
        "id": c.id,
        "name": c.name,
        "country": "",
        "lat": c.lat,
        "lng": c.lng,
        "rating": c.rating,
        "players": c.players,
        "safety": c.safety,
        "tax": c.tax,
        "radius_km": c.radius_km,
        "mayor_user_id": c.mayor_user_id
    } for c in q.all()]

    return jsonify({"cities": cities})

@cities_bp.get("/api/cities/<int:city_id>")
def city_detail(city_id: int):
    c = City.query.get_or_404(city_id)
    return jsonify({
        "id": c.id,
        "name": c.name,
        "country": "",
        "lat": c.lat,
        "lng": c.lng,
        "rating": c.rating,
        "players": c.players,
        "safety": c.safety,
        "tax": c.tax,
        "radius_km": c.radius_km,
        "mayor_user_id": c.mayor_user_id
    })

@cities_bp.post("/api/cities/create")
@login_required
def create_city():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    lat = data.get("lat")
    lng = data.get("lng")
    radius_km = float(data.get("radius_km") or 15.0)

    if not name:
        return jsonify({"error": "name required"}), 400
    if lat is None or lng is None:
        return jsonify({"error": "lat/lng required"}), 400
    if len(name) < 3 or len(name) > 32:
        return jsonify({"error": "name length 3..32"}), 400
    if radius_km < 5 or radius_km > 200:
        return jsonify({"error": "radius_km must be 5..200"}), 400

    cost = 5000
    if current_user.balance < cost:
        return jsonify({"error": f"not enough balance (need {cost})"}), 402

    current_user.balance -= cost

    c = City(
        name=name,
        lat=float(lat),
        lng=float(lng),
        radius_km=radius_km,
        mayor_user_id=current_user.id,
        tax=5.0,
        rating=50,
        safety="Medium",
        players=0
    )
    db.session.add(c)
    db.session.flush()

    current_user.role = "mayor"

    _audit("city", c.id, "city_created", {
        "name": c.name, "lat": c.lat, "lng": c.lng,
        "radius_km": c.radius_km, "cost": cost
    })

    db.session.commit()

    return jsonify({
        "ok": True,
        "city": {
            "id": c.id,
            "name": c.name,
            "lat": c.lat,
            "lng": c.lng,
            "radius_km": c.radius_km,
            "mayor_user_id": c.mayor_user_id
        }
    }), 201

@cities_bp.post("/api/cities/<int:city_id>/expand")
@login_required
def expand_city(city_id: int):
    c = City.query.get_or_404(city_id)

    if c.mayor_user_id != current_user.id:
        return jsonify({"error": "only mayor can expand"}), 403

    data = request.get_json(force=True, silent=True) or {}
    add_km = float(data.get("add_km") or 1.0)

    if add_km <= 0 or add_km > 25:
        return jsonify({"error": "add_km must be 1..25"}), 400

    base = 200
    cost = int(base * add_km * (1 + (c.radius_km / 50.0)))

    if current_user.balance < cost:
        return jsonify({"error": f"not enough balance (need {cost})"}), 402

    current_user.balance -= cost
    old = c.radius_km
    c.radius_km = float(c.radius_km + add_km)

    _audit("city", c.id, "territory_expanded", {
        "old_radius_km": old,
        "add_km": add_km,
        "new_radius_km": c.radius_km,
        "cost": cost
    })

    db.session.commit()

    return jsonify({"ok": True, "cost": cost, "new_radius_km": c.radius_km})
