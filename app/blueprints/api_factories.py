from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from ..extensions import db
from ..models import Factory, Country
from ..services.geo import point_in_polygon
from ..services.resources import get_resource_nodes
from ..services.economy import (
    FACTORY_BLUEPRINTS, FACTORY_MAX_PER_COUNTRY, FACTORY_PLACE_FEE,
    accrue_factory, calc_factory_rate_per_hour, resources_near_point_in_country,
    country_polygon_ring
)

bp_api_factories = Blueprint("api_factories", __name__)

@bp_api_factories.get("/api/factories")
def api_factories_list():
    items = Factory.query.order_by(Factory.created_at.asc()).all()
    fc = {"type": "FeatureCollection", "features": [f.to_feature() for f in items]}
    return jsonify(ok=True, data=fc)

@bp_api_factories.get("/api/my/factories")
@login_required
def api_my_factories():
    if getattr(current_user, "is_blocked", False):
        return jsonify(ok=False, error="Blocked"), 403

    nodes = get_resource_nodes()
    now = datetime.utcnow()
    items = Factory.query.filter_by(owner_user_id=current_user.id).all()
    out = []
    for f in items:
        accrue_factory(nodes, f, now)
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
            "rate_per_hour": float(calc_factory_rate_per_hour(nodes, f)),
        })
    db.session.commit()
    return jsonify(ok=True, data=out, coins=int(current_user.coins or 0))

@bp_api_factories.post("/api/factories")
@login_required
def api_factory_build():
    if getattr(current_user, "is_blocked", False):
        return jsonify(ok=False, error="Blocked"), 403
    if not current_user.is_confirmed:
        return jsonify(ok=False, error="Email not confirmed"), 403

    nodes = get_resource_nodes()

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

    ring = country_polygon_ring(country)
    if not ring or not point_in_polygon(float(lng), float(lat), ring):
        return jsonify(ok=False, error="Точку треба ставити ВСЕРЕДИНІ своєї країни."), 400

    bp = FACTORY_BLUEPRINTS[blueprint]
    total_cost = int(bp["build_cost"]) + int(FACTORY_PLACE_FEE)

    if int(current_user.coins or 0) < total_cost:
        return jsonify(ok=False, error=f"Недостатньо монет. Треба {total_cost} EC."), 400

    near = resources_near_point_in_country(nodes, country, float(lng), float(lat))
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
        return jsonify(ok=False, error=f"Нема потрібних ресурсів поруч: {', '.join(missing)} (радіус {__import__('os').getenv('FACTORY_PICK_RADIUS_KM','120')} км)."), 400

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

@bp_api_factories.post("/api/factories/<int:fid>/collect")
@login_required
def api_factory_collect(fid: int):
    if getattr(current_user, "is_blocked", False):
        return jsonify(ok=False, error="Blocked"), 403

    nodes = get_resource_nodes()

    f = db.session.get(Factory, fid)
    if not f:
        return jsonify(ok=False, error="Factory not found"), 404
    if f.owner_user_id != current_user.id:
        return jsonify(ok=False, error="Not yours"), 403

    now = datetime.utcnow()
    accrue_factory(nodes, f, now)

    amount = int(f.stored_coins or 0)
    if amount <= 0:
        db.session.commit()
        return jsonify(ok=True, collected=0, coins=int(current_user.coins or 0))

    f.stored_coins = 0
    current_user.coins = int(current_user.coins or 0) + amount
    db.session.commit()

    return jsonify(ok=True, collected=amount, coins=int(current_user.coins or 0))

@bp_api_factories.post("/api/factories/<int:fid>/upgrade")
@login_required
def api_factory_upgrade(fid: int):
    if getattr(current_user, "is_blocked", False):
        return jsonify(ok=False, error="Blocked"), 403

    nodes = get_resource_nodes()

    f = db.session.get(Factory, fid)
    if not f:
        return jsonify(ok=False, error="Factory not found"), 404
    if f.owner_user_id != current_user.id:
        return jsonify(ok=False, error="Not yours"), 403

    now = datetime.utcnow()
    accrue_factory(nodes, f, now)

    next_lvl = int(f.level or 1) + 1
    cost = int(260 * (next_lvl ** 1.55))

    if int(current_user.coins or 0) < cost:
        return jsonify(ok=False, error=f"Not enough coins. Need {cost} EC."), 400

    current_user.coins = int(current_user.coins or 0) - cost
    f.level = next_lvl
    db.session.commit()

    return jsonify(ok=True, level=int(f.level), coins=int(current_user.coins or 0))
