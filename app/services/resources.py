import os
import math
import random
import logging
from .geo import haversine_km
from .land import point_on_land, load_land_geojson

log = logging.getLogger("earthcity")

RESOURCE_NODES_BASE = [
    {"type": "oil", "name": "Oil Basin", "lng": 50.5, "lat": 24.0, "strength": 0.95},
    {"type": "oil", "name": "Oil Field", "lng": 44.0, "lat": 30.0, "strength": 0.78},
    {"type": "oil", "name": "Oil Sands", "lng": -113.5, "lat": 56.0, "strength": 0.66},
    {"type": "oil", "name": "Offshore Oil", "lng": 6.5, "lat": 53.2, "strength": 0.71},

    {"type": "gas", "name": "Gas Field", "lng": 56.0, "lat": 25.5, "strength": 0.86},
    {"type": "gas", "name": "Gas Field", "lng": 36.0, "lat": 31.0, "strength": 0.72},
    {"type": "gas", "name": "Gas Field", "lng": 65.0, "lat": 39.0, "strength": 0.77},
    {"type": "gas", "name": "Gas Field", "lng": 133.0, "lat": -23.0, "strength": 0.73},

    {"type": "iron", "name": "Iron Ore", "lng": 32.2, "lat": 47.8, "strength": 0.88},
    {"type": "iron", "name": "Iron Deposit", "lng": 107.0, "lat": 52.0, "strength": 0.67},
    {"type": "iron", "name": "Iron Ore", "lng": -74.0, "lat": 5.0, "strength": 0.70},

    {"type": "gold", "name": "Gold", "lng": -2.0, "lat": 7.0, "strength": 0.72},
    {"type": "gold", "name": "Gold", "lng": 120.5, "lat": -3.0, "strength": 0.60},

    {"type": "rare", "name": "Rare Minerals", "lng": 28.0, "lat": -3.0, "strength": 0.78},
    {"type": "rare", "name": "Rare Minerals", "lng": 103.0, "lat": 26.0, "strength": 0.70},

    {"type": "uranium", "name": "Uranium", "lng": 133.0, "lat": -22.0, "strength": 0.72},

    {"type": "coal", "name": "Coal", "lng": 24.5, "lat": 49.5, "strength": 0.82},
    {"type": "coal", "name": "Coal", "lng": 88.0, "lat": 23.0, "strength": 0.70},
    {"type": "coal", "name": "Coal", "lng": 147.0, "lat": -33.0, "strength": 0.66},

    {"type": "water", "name": "Fresh Water", "lng": 90.0, "lat": 23.8, "strength": 0.90},
    {"type": "water", "name": "Fresh Water", "lng": 30.5, "lat": -1.3, "strength": 0.76},
    {"type": "water", "name": "Fresh Water", "lng": 137.0, "lat": 36.0, "strength": 0.74},

    {"type": "farmland", "name": "Farmland", "lng": 31.2, "lat": 49.2, "strength": 0.88},
    {"type": "farmland", "name": "Farmland", "lng": 10.5, "lat": 50.7, "strength": 0.74},
    {"type": "farmland", "name": "Farmland", "lng": -58.0, "lat": -34.5, "strength": 0.66},

    {"type": "fish", "name": "Fishing Zone", "lng": 142.0, "lat": 41.5, "strength": 0.72},
    {"type": "fish", "name": "Fishing Zone", "lng": 16.0, "lat": 55.5, "strength": 0.68},

    {"type": "wind", "name": "Wind Zone", "lng": 8.0, "lat": 56.0, "strength": 0.75},
    {"type": "wind", "name": "Wind Zone", "lng": 145.0, "lat": -35.0, "strength": 0.73},

    {"type": "solar", "name": "Solar", "lng": 25.0, "lat": 23.0, "strength": 0.86},
    {"type": "solar", "name": "Solar", "lng": -112.0, "lat": 34.0, "strength": 0.78},

    {"type": "hydro", "name": "Hydro Potential", "lng": 85.0, "lat": 28.0, "strength": 0.78},
    {"type": "geo", "name": "Geothermal", "lng": -21.9, "lat": 64.9, "strength": 0.64},
]

RESOURCE_TOTAL_TARGET = int(os.getenv("RESOURCE_TOTAL_TARGET", "950"))
RESOURCE_MIN_DIST_KM = float(os.getenv("RESOURCE_MIN_DIST_KM", "55"))
RESOURCE_GEN_TRIES = int(os.getenv("RESOURCE_GEN_TRIES", "65000"))

def _clamp(v, a, b):
    return max(a, min(b, v))

def _make_cluster_name(rtype: str, i: int) -> str:
    pretty = {
        "oil": "Oil", "gas": "Gas", "iron": "Iron", "gold": "Gold", "coal": "Coal",
        "uranium": "Uranium", "rare": "Rare", "water": "Water", "farmland": "Farmland",
        "fish": "Fishing", "wind": "Wind", "solar": "Solar", "hydro": "Hydro", "geo": "Geo",
    }.get(rtype, rtype.title())
    return f"{pretty} Node #{i}"

def generate_more_resources():
    rng = random.Random(13371337)
    nodes = [dict(x) for x in RESOURCE_NODES_BASE]

    grid = {}
    cell_deg = 2.0

    def cell_key(lng, lat):
        return (int((lng + 180) / cell_deg), int((lat + 90) / cell_deg))

    def nearby_cells(lng, lat):
        cx, cy = cell_key(lng, lat)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                yield (cx + dx, cy + dy)

    for n in nodes:
        k = cell_key(n["lng"], n["lat"])
        grid.setdefault(k, []).append((n["lng"], n["lat"]))

    type_weights = {
        "oil": 1.0, "gas": 1.0, "iron": 1.15, "coal": 1.10, "gold": 0.7,
        "rare": 0.55, "uranium": 0.35, "water": 1.2, "farmland": 1.2,
        "fish": 0.85, "wind": 0.95, "solar": 0.95, "hydro": 0.75, "geo": 0.45,
    }

    anchors_by_type = {}
    for n in RESOURCE_NODES_BASE:
        anchors_by_type.setdefault(n["type"], []).append(n)

    types = list(type_weights.keys())
    weights = [type_weights[t] for t in types]

    def pick_type():
        return rng.choices(types, weights=weights, k=1)[0]

    spread_deg_by_type = {
        "oil": 7.0, "gas": 7.0, "iron": 6.0, "coal": 6.5, "gold": 5.0,
        "rare": 4.5, "uranium": 4.0, "water": 7.0, "farmland": 7.0,
        "fish": 6.0, "wind": 7.5, "solar": 7.5, "hydro": 5.5, "geo": 4.0,
    }

    feats = load_land_geojson()
    land_strict = bool(feats)

    def ok_place(lng, lat):
        if lng < -180 or lng > 180 or lat < -90 or lat > 90:
            return False
        if land_strict and not point_on_land(lng, lat):
            return False
        for ck in nearby_cells(lng, lat):
            for (olng, olat) in grid.get(ck, []):
                if haversine_km(lng, lat, olng, olat) < RESOURCE_MIN_DIST_KM:
                    return False
        return True

    next_idx = 1

    for _ in range(RESOURCE_GEN_TRIES):
        if len(nodes) >= RESOURCE_TOTAL_TARGET:
            break

        rtype = pick_type()
        anchors = anchors_by_type.get(rtype) or RESOURCE_NODES_BASE
        a = rng.choice(anchors)

        spread = spread_deg_by_type.get(rtype, 6.0)
        lng = float(a["lng"]) + rng.gauss(0, spread)
        lat = float(a["lat"]) + rng.gauss(0, spread * 0.72)

        lng = _clamp(lng, -179.8, 179.8)
        lat = _clamp(lat, -85.0, 85.0)

        if not ok_place(lng, lat):
            continue

        base_strength = float(a.get("strength", 0.65))
        strength = _clamp(base_strength + rng.uniform(-0.22, 0.18), 0.35, 0.99)

        nodes.append({
            "type": rtype,
            "name": _make_cluster_name(rtype, next_idx),
            "lng": lng,
            "lat": lat,
            "strength": strength
        })
        next_idx += 1

        k = cell_key(lng, lat)
        grid.setdefault(k, []).append((lng, lat))

    log.info("Resources generated: %d (target %d, land_strict=%s)", len(nodes), RESOURCE_TOTAL_TARGET, land_strict)
    return nodes

# IMPORTANT: lazy init — буде ініціалізовано коли вперше треба (в api_world)
RESOURCE_NODES = None

def get_resource_nodes():
    global RESOURCE_NODES
    if RESOURCE_NODES is None:
        RESOURCE_NODES = generate_more_resources()
    return RESOURCE_NODES

def parse_bbox(s: str):
    if not s:
        return None
    try:
        parts = [float(x.strip()) for x in s.split(",")]
        if len(parts) != 4:
            return None
        w, s_, e, n = parts
        w = max(-180.0, min(180.0, w))
        e = max(-180.0, min(180.0, e))
        s_ = max(-90.0, min(90.0, s_))
        n = max(-90.0, min(90.0, n))
        return (w, s_, e, n)
    except Exception:
        return None

def in_bbox(lng: float, lat: float, bbox):
    w, s, e, n = bbox
    if lat < s or lat > n:
        return False
    if w <= e:
        return (w <= lng <= e)
    return (lng >= w) or (lng <= e)
