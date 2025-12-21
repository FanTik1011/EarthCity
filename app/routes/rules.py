from flask import Blueprint, jsonify, current_app
from ..constants import RESOURCE_NODES, FACTORY_BLUEPRINTS

rules_bp = Blueprint("rules_bp", __name__)

@rules_bp.get("/api/rules")
def api_rules():
    c = current_app.config
    return jsonify(ok=True, rules={
        "start_coins": c["START_COINS"],
        "country_base_cost": c["COUNTRY_BASE_COST"],
        "country_cost_per_1000_km2": c["COUNTRY_COST_PER_1000_KM2"],
        "country_max_area_km2": c["COUNTRY_MAX_AREA_KM2"],
        "country_max_points": c["COUNTRY_MAX_POINTS"],
        "factory_place_fee": c["FACTORY_PLACE_FEE"],
        "factory_pick_radius_km": c["FACTORY_PICK_RADIUS_KM"],
        "factory_max_per_country": c["FACTORY_MAX_PER_COUNTRY"],
    })

@rules_bp.get("/api/resources")
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

@rules_bp.get("/api/blueprints")
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
