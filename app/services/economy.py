import os
import json
import math
from datetime import datetime
from ..extensions import db
from ..models import Country, Factory
from .geo import haversine_km  # ✅ only this now

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

FACTORY_BLUEPRINTS = {
    "steel_mill": {"name": "Steel Mill", "icon": "🏗️", "desc": "Iron+Coal → profit", "build_cost": 900, "upkeep": 0, "base_income_per_hour": 70, "requires": {"iron": 1, "coal": 1}},
    "oil_refinery": {"name": "Oil Refinery", "icon": "🛢️", "desc": "Oil → money", "build_cost": 1100, "upkeep": 0, "base_income_per_hour": 95, "requires": {"oil": 1}},
    "gas_plant": {"name": "Gas Plant", "icon": "🔥", "desc": "Gas → profit", "build_cost": 980, "upkeep": 0, "base_income_per_hour": 82, "requires": {"gas": 1}},
    "hydro_plant": {"name": "Hydro Plant", "icon": "🌊", "desc": "Hydro → profit", "build_cost": 950, "upkeep": 0, "base_income_per_hour": 78, "requires": {"hydro": 1}},
    "farm_complex": {"name": "Farm Complex", "icon": "🌾", "desc": "Farmland → profit", "build_cost": 650, "upkeep": 0, "base_income_per_hour": 52, "requires": {"farmland": 1}},
    "waterworks": {"name": "Waterworks", "icon": "💧", "desc": "Water → profit", "build_cost": 720, "upkeep": 0, "base_income_per_hour": 50, "requires": {"water": 1}},
    "rare_lab": {"name": "Rare Lab", "icon": "💎", "desc": "Rare → big profit", "build_cost": 1400, "upkeep": 0, "base_income_per_hour": 130, "requires": {"rare": 1}},
    "gold_mint": {"name": "Gold Mint", "icon": "🪙", "desc": "Gold → big profit", "build_cost": 1350, "upkeep": 0, "base_income_per_hour": 125, "requires": {"gold": 1}},
    "shipyard": {"name": "Shipyard", "icon": "⚓", "desc": "Fish → profit", "build_cost": 1000, "upkeep": 0, "base_income_per_hour": 88, "requires": {"fish": 1}},
}

def compute_country_cost(area_km2: float) -> int:
    return int(round(COUNTRY_BASE_COST + (area_km2 / 1000.0) * COUNTRY_COST_PER_1000_KM2))


# ----------------------------
# ✅ Local point-in-polygon (ring) for economy usage
# ----------------------------
def point_in_ring(lng: float, lat: float, ring) -> bool:
    """
    Ray casting. ring must be closed.
    """
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


def country_outer_rings(country: Country):
    """
    ✅ Supports Polygon + MultiPolygon (after union attach)
    Returns list of outer rings.
    """
    try:
        geom = json.loads(country.geom_json)
    except Exception:
        return []

    t = geom.get("type")
    coords = geom.get("coordinates")

    rings = []
    if t == "Polygon" and isinstance(coords, list) and coords and isinstance(coords[0], list):
        rings.append(coords[0])
    elif t == "MultiPolygon" and isinstance(coords, list):
        for poly in coords:
            if isinstance(poly, list) and poly and isinstance(poly[0], list):
                rings.append(poly[0])

    # filter closed-ish rings
    rings = [r for r in rings if isinstance(r, list) and len(r) >= 4]
    return rings


def point_in_country(country: Country, lng: float, lat: float) -> bool:
    """
    ✅ Works for Polygon/MultiPolygon by checking all outer rings.
    (holes ignored; ok for this game logic)
    """
    for ring in country_outer_rings(country):
        if point_in_ring(lng, lat, ring):
            return True
    return False


def resources_near_point_in_country(resource_nodes, country: Country, lng: float, lat: float):
    near = []
    for n in resource_nodes:
        if not point_in_country(country, float(n["lng"]), float(n["lat"])):
            continue
        if haversine_km(lng, lat, n["lng"], n["lat"]) <= FACTORY_PICK_RADIUS_KM:
            near.append(n)
    return near


def calc_factory_rate_per_hour(resource_nodes, factory: Factory) -> float:
    bp = FACTORY_BLUEPRINTS.get(factory.blueprint)
    if not bp:
        return 0.0

    base = float(bp.get("base_income_per_hour", 0))
    level = int(factory.level or 1)

    country = db.session.get(Country, factory.country_id)
    if not country:
        return 0.0

    near = resources_near_point_in_country(resource_nodes, country, factory.lng, factory.lat)
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


def accrue_factory(resource_nodes, factory: Factory, now: datetime):
    last = factory.last_collected_at or now
    dt_hours = (now - last).total_seconds() / 3600.0
    if dt_hours <= 0:
        return

    dt_hours = min(dt_hours, FACTORY_ACCUM_CAP_HOURS)

    rate = calc_factory_rate_per_hour(resource_nodes, factory)
    gain = int(math.floor(rate * dt_hours))
    if gain > 0:
        factory.stored_coins = int(factory.stored_coins or 0) + gain
    factory.last_collected_at = now
def country_polygon_ring(country: Country):
    """
    Backward-compatible for old code (api_factories.py etc).
    Returns ONE outer ring.
    If geometry is MultiPolygon -> returns the biggest outer ring (roughly).
    """
    rings = country_outer_rings(country)
    if not rings:
        return None
    if len(rings) == 1:
        return rings[0]

    # choose biggest ring by bbox area (fast heuristic)
    def bbox_area(r):
        xs = [p[0] for p in r[:-1]]
        ys = [p[1] for p in r[:-1]]
        return (max(xs) - min(xs)) * (max(ys) - min(ys))

    return max(rings, key=bbox_area)
