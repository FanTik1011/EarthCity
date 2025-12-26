import json
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from ..extensions import db
from ..models import Country, Factory
from ..services.land import polygon_is_on_land
from ..services.geo import polygon_area_km2_equirect, geom_intersects_any_country, geom_intersects_any_country_except
from ..services.economy import (
    COUNTRY_MAX_AREA_KM2, COUNTRY_MAX_POINTS, COUNTRY_MIN_POINTS,
    compute_country_cost
)

bp_api_countries = Blueprint("api_countries", __name__)

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

@bp_api_countries.get("/api/countries")
def api_countries_list():
    countries = Country.query.order_by(Country.created_at.asc()).all()
    fc = {"type": "FeatureCollection", "features": [c.to_feature() for c in countries]}
    return jsonify(ok=True, data=fc)

@bp_api_countries.post("/api/countries")
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

    if not polygon_is_on_land(geom):
        return jsonify(ok=False, error="Країну можна створювати лише на суші (не на морі/океані)."), 400

    if geom_intersects_any_country(geom):
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
        geom_json=json.dumps(geom, ensure_ascii=False)
    )
    db.session.add(country)
    db.session.commit()

    return jsonify(ok=True, country=country.to_feature(), coins=int(current_user.coins or 0))

@bp_api_countries.get("/api/my/country")
@login_required
def api_my_country():
    if getattr(current_user, "is_blocked", False):
        return jsonify(ok=False, error="Blocked"), 403
    c = Country.query.filter_by(owner_user_id=current_user.id).first()
    if not c:
        return jsonify(ok=True, data=None)
    return jsonify(ok=True, data=c.to_feature())

@bp_api_countries.post("/api/countries/<int:cid>/update-geometry")
@login_required
def api_country_update_geometry(cid: int):
    if getattr(current_user, "is_blocked", False):
        return jsonify(ok=False, error="Blocked"), 403
    if not current_user.is_confirmed:
        return jsonify(ok=False, error="Email not confirmed"), 403

    c = db.session.get(Country, cid)
    if not c:
        return jsonify(ok=False, error="Country not found"), 404
    if c.owner_user_id != current_user.id:
        return jsonify(ok=False, error="Not your country"), 403

    data = request.get_json(force=True, silent=True) or {}
    geom = data.get("geometry")

    ok, err = _validate_polygon(geom)
    if not ok:
        return jsonify(ok=False, error=err), 400

    if not polygon_is_on_land(geom):
        return jsonify(ok=False, error="Країну можна тримати лише на суші (не на морі/океані)."), 400

    if geom_intersects_any_country_except(geom, exclude_country_id=c.id):
        return jsonify(ok=False, error="Не можна розширити на іншу країну (перетин)."), 400

    new_area = polygon_area_km2_equirect(geom)
    if new_area > COUNTRY_MAX_AREA_KM2:
        return jsonify(ok=False, error=f"Занадто велика: {int(new_area):,} км² (макс {COUNTRY_MAX_AREA_KM2:,} км²)"), 400

    old_area = float(c.area_km2 or 0.0)

    old_cost = compute_country_cost(old_area)
    new_cost = compute_country_cost(new_area)
    delta = int(new_cost - old_cost)

    if delta > 0:
        if int(current_user.coins or 0) < delta:
            return jsonify(ok=False, error=f"Недостатньо монет. Треба {delta} EC (за розширення)."), 400
        current_user.coins = int(current_user.coins or 0) - delta

    c.geom_json = json.dumps(geom, ensure_ascii=False)
    c.area_km2 = float(new_area)

    db.session.commit()
    return jsonify(ok=True, country=c.to_feature(), coins=int(current_user.coins or 0), delta_cost=delta)

@bp_api_countries.get("/api/countries/<int:cid>")
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
