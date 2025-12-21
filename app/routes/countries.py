import json
from flask import Blueprint, jsonify, request, current_app
from flask_login import current_user

from ..extensions import db
from ..models import Country, Factory
from ..services.geo import polygon_area_km2_equirect
from ..services.economy import compute_country_cost

countries_bp = Blueprint("countries_bp", __name__)

def _validate_polygon(geom: dict):
    c = current_app.config
    if not isinstance(geom, dict):
        return False, "Geometry must be object"
    if geom.get("type") != "Polygon":
        return False, "Only Polygon supported"
    coords = geom.get("coordinates")
    if not isinstance(coords, list) or len(coords) < 1:
        return False, "Polygon coordinates invalid"
    ring = coords[0]
    if not isinstance(ring, list) or len(ring) < (c["COUNTRY_MIN_POINTS"] + 1):
        return False, f"Polygon ring must have {c['COUNTRY_MIN_POINTS']+1}+ points"
    if len(ring) > (c["COUNTRY_MAX_POINTS"] + 1):
        return False, f"Too many points (max {c['COUNTRY_MAX_POINTS']})"
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

@countries_bp.get("/api/countries")
def api_countries_list():
    countries = Country.query.order_by(Country.created_at.asc()).all()
    fc = {"type": "FeatureCollection", "features": [c.to_feature() for c in countries]}
    return jsonify(ok=True, data=fc)

@countries_bp.post("/api/countries")
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
    if area_km2 > current_app.config["COUNTRY_MAX_AREA_KM2"]:
        return jsonify(ok=False, error=f"Країна занадто велика: {int(area_km2):,} км² (макс {current_app.config['COUNTRY_MAX_AREA_KM2']:,} км²)"), 400

    cost = compute_country_cost(area_km2, current_app.config["COUNTRY_BASE_COST"], current_app.config["COUNTRY_COST_PER_1000_KM2"])
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

@countries_bp.get("/api/countries/<int:cid>")
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
    })
