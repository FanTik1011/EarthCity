import os
import json
import logging
from flask import current_app
from .geo import point_in_polygon

log = logging.getLogger("earthcity")

LAND_FEATURES = None

def _land_path():
    return os.path.join(current_app.root_path, "static", "data", "land.geojson")

def load_land_geojson():
    global LAND_FEATURES
    if LAND_FEATURES is not None:
        return LAND_FEATURES

    path = _land_path()
    if not os.path.exists(path):
        log.warning("land.geojson not found at %s (sea check disabled)", path)
        LAND_FEATURES = []
        return LAND_FEATURES

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        LAND_FEATURES = data.get("features") or []
        log.info("Loaded land.geojson features: %d", len(LAND_FEATURES))
        return LAND_FEATURES
    except Exception as e:
        log.warning("Failed to load land.geojson (%s). Sea check disabled.", e)
        LAND_FEATURES = []
        return LAND_FEATURES

def rings_from_geom(geom: dict):
    if not geom or not isinstance(geom, dict):
        return []
    gtype = geom.get("type")
    coords = geom.get("coordinates")

    rings = []
    if gtype == "Polygon":
        if isinstance(coords, list) and coords and isinstance(coords[0], list):
            ring = coords[0]
            if isinstance(ring, list) and len(ring) >= 4:
                rings.append(ring)
    elif gtype == "MultiPolygon":
        if isinstance(coords, list):
            for poly in coords:
                if not poly or not isinstance(poly, list):
                    continue
                ring = poly[0] if poly and isinstance(poly[0], list) else None
                if isinstance(ring, list) and len(ring) >= 4:
                    rings.append(ring)
    return rings

def point_on_land(lng: float, lat: float) -> bool:
    feats = load_land_geojson()
    if not feats:
        return True  # sea check disabled

    for feat in feats:
        g = (feat or {}).get("geometry") or {}
        for ring in rings_from_geom(g):
            if point_in_polygon(lng, lat, ring):
                return True
    return False

def polygon_is_on_land(geom: dict) -> bool:
    ring = (geom.get("coordinates") or [[]])[0]
    pts = ring[:-1]
    if not pts:
        return False
    for lng, lat in pts:
        if not point_on_land(float(lng), float(lat)):
            return False
    return True
