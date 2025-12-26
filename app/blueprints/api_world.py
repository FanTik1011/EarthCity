from flask import Blueprint, request, jsonify
from ..services.economy import (
    COUNTRY_BASE_COST, COUNTRY_COST_PER_1000_KM2, COUNTRY_MAX_AREA_KM2, COUNTRY_MAX_POINTS,
    FACTORY_PLACE_FEE, FACTORY_PICK_RADIUS_KM, FACTORY_MAX_PER_COUNTRY,
    FACTORY_BLUEPRINTS
)
from ..services.resources import get_resource_nodes, parse_bbox, in_bbox

bp_api_world = Blueprint("api_world", __name__)

@bp_api_world.get("/api/rules")
def api_rules():
    return jsonify(ok=True, rules={
        "country_base_cost": COUNTRY_BASE_COST,
        "country_cost_per_1000_km2": COUNTRY_COST_PER_1000_KM2,
        "country_max_area_km2": COUNTRY_MAX_AREA_KM2,
        "country_max_points": COUNTRY_MAX_POINTS,
        "factory_place_fee": FACTORY_PLACE_FEE,
        "factory_pick_radius_km": FACTORY_PICK_RADIUS_KM,
        "factory_max_per_country": FACTORY_MAX_PER_COUNTRY
    })

@bp_api_world.get("/api/blueprints")
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

@bp_api_world.get("/api/resources")
def api_resources():
    nodes_all = get_resource_nodes()

    bbox = parse_bbox(request.args.get("bbox", "") or "")
    try:
        zoom = float(request.args.get("zoom", "") or "0")
    except Exception:
        zoom = 0.0

    try:
        limit = int(request.args.get("limit", "") or "0")
    except Exception:
        limit = 0

    nodes = nodes_all
    if bbox:
        nodes = [n for n in nodes_all if in_bbox(float(n["lng"]), float(n["lat"]), bbox)]

    if not bbox and limit <= 0 and zoom <= 0:
        fc = {"type": "FeatureCollection", "features": []}
        for idx, n in enumerate(nodes_all, start=1):
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

    if zoom < 1.6:
        cell_deg = 6.0
    elif zoom < 2.3:
        cell_deg = 3.5
    elif zoom < 3.2:
        cell_deg = 2.2
    elif zoom < 4.2:
        cell_deg = 1.2
    else:
        cell_deg = 0.6

    buckets = {}
    for n in nodes:
        lng = float(n["lng"])
        lat = float(n["lat"])
        rtype = n.get("type") or "unknown"
        cx = int((lng + 180.0) // cell_deg)
        cy = int((lat + 90.0) // cell_deg)
        key = (cx, cy, rtype)

        b = buckets.get(key)
        if not b:
            buckets[key] = {
                "type": rtype,
                "name": n.get("name") or rtype,
                "lng_sum": lng,
                "lat_sum": lat,
                "count": 1,
                "best_strength": float(n.get("strength", 0.5)),
            }
        else:
            b["lng_sum"] += lng
            b["lat_sum"] += lat
            b["count"] += 1
            b["best_strength"] = max(b["best_strength"], float(n.get("strength", 0.5)))

    items = list(buckets.values())
    items.sort(key=lambda x: (x["best_strength"], x["count"]), reverse=True)

    if limit and limit > 0:
        items = items[: max(10, min(limit, 12000))]

    fc = {"type": "FeatureCollection", "features": []}
    for idx, it in enumerate(items, start=1):
        lng = it["lng_sum"] / it["count"]
        lat = it["lat_sum"] / it["count"]
        props = {
            "type": it["type"],
            "name": it["name"],
            "strength": float(it["best_strength"]),
            "count": int(it["count"]),
        }
        fc["features"].append({
            "type": "Feature",
            "id": idx,
            "properties": props,
            "geometry": {"type": "Point", "coordinates": [float(lng), float(lat)]}
        })

    return jsonify(ok=True, data=fc)
