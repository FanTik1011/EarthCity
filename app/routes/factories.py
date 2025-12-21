import math
from datetime import datetime

from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user

from ..extensions import db
from ..models import Factory, Country
from ..constants import RESOURCE_NODES, FACTORY_BLUEPRINTS
from ..services.geo import country_polygon_ring, point_in_polygon, haversine_km

factories_bp = Blueprint("factories_bp", __name__)

def _resources_near_point_in_country(country: Country, lng: float, lat: float):
    ring = country_polygon_ring(country.geom_json)
    if not ring:
        return []

    near = []
    for n in RESOURCE_NODES:
        if not point_in_polygon(n["lng"], n["lat"], ring):
            continue
        if haversine_km(lng, lat, n["lng"], n["lat"]) <= current_app.config["FACTORY_PICK_RADIUS_KM"]:
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

    dt_hours = min(dt_hours, current_app.config["FACTORY_ACCUM_CAP_HOURS"])
    rate = _calc_factory_rate_per_hour(factory)
    gain = int(math.floor(rate * dt_hours))
    if gain > 0:
        factory.stored_coins = int(factory.stored_coins or 0) + gain
    factory.last_collected_at = now

@factories_bp.get("/api/factories")
def api_factories_list():
    items = Factory.query.order_by(Factory.created_at.asc()).all()
    fc = {"type": "FeatureCollection", "features": [f.to_feature() for f in items]}
    return jsonify(ok=True, data=fc)

@factories_bp.get("/api/my/factories")
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

@factories_bp.post("/api/factories")
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
    if cnt >= current_app.config["FACTORY_MAX_PER_COUNTRY"]:
        return jsonify(ok=False, error=f"Factory limit reached (max {current_app.config['FACTORY_MAX_PER_COUNTRY']})"), 400

    ring = country_polygon_ring(country.geom_json)
    if not ring or not point_in_polygon(float(lng), float(lat), ring):
        return jsonify(ok=False, error="Точку треба ставити ВСЕРЕДИНІ своєї країни."), 400

    bp = FACTORY_BLUEPRINTS[blueprint]
    total_cost = int(bp["build_cost"]) + int(current_app.config["FACTORY_PLACE_FEE"])

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
        return jsonify(ok=False, error=f"Нема потрібних ресурсів поруч: {', '.join(missing)} (радіус {current_app.config['FACTORY_PICK_RADIUS_KM']} км)."), 400

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

@factories_bp.post("/api/factories/<int:fid>/collect")
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

@factories_bp.post("/api/factories/<int:fid>/upgrade")
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
