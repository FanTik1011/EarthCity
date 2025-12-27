# services/land.py
import os
import json
import logging
from flask import current_app

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


# ------------------------
# Geometry helpers
# ------------------------
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


def ring_bbox(ring):
    xs = [p[0] for p in ring[:-1]]
    ys = [p[1] for p in ring[:-1]]
    return (min(xs), min(ys), max(xs), max(ys))


def bbox_contains(b, lng, lat) -> bool:
    minx, miny, maxx, maxy = b
    return (minx <= lng <= maxx) and (miny <= lat <= maxy)


def land_rings_from_geom(geom: dict):
    """
    Returns list of (outer_ring, holes_rings_list)
    Supports Polygon and MultiPolygon.
    """
    if not geom or not isinstance(geom, dict):
        return []
    gtype = geom.get("type")
    coords = geom.get("coordinates")

    out = []

    if gtype == "Polygon" and isinstance(coords, list) and coords:
        outer = coords[0] if isinstance(coords[0], list) else None
        holes = [r for r in coords[1:] if isinstance(r, list)]
        if isinstance(outer, list) and len(outer) >= 4:
            out.append((outer, holes))

    elif gtype == "MultiPolygon" and isinstance(coords, list):
        for poly in coords:
            if not isinstance(poly, list) or not poly:
                continue
            outer = poly[0] if isinstance(poly[0], list) else None
            holes = [r for r in poly[1:] if isinstance(r, list)]
            if isinstance(outer, list) and len(outer) >= 4:
                out.append((outer, holes))

    return out


# ------------------------
# Public API
# ------------------------
def point_on_land(lng: float, lat: float) -> bool:
    feats = load_land_geojson()
    if not feats:
        return True  # sea check disabled

    for feat in feats:
        g = (feat or {}).get("geometry") or {}
        for outer, holes in land_rings_from_geom(g):
            # bbox quick reject
            b = ring_bbox(outer)
            if not bbox_contains(b, lng, lat):
                continue

            # inside outer?
            if not point_in_ring(lng, lat, outer):
                continue

            # if inside any hole => NOT land
            in_hole = False
            for h in holes:
                if len(h) >= 4:
                    hb = ring_bbox(h)
                    if bbox_contains(hb, lng, lat) and point_in_ring(lng, lat, h):
                        in_hole = True
                        break
            if not in_hole:
                return True

    return False


def iter_polygon_points(geom: dict):
    """
    Yields points from GeoJSON Polygon or MultiPolygon (outer rings only)
    We validate on outer rings; holes are ignored for simplicity.
    """
    if not isinstance(geom, dict):
        return
    t = geom.get("type")
    coords = geom.get("coordinates")

    if t == "Polygon" and isinstance(coords, list) and coords:
        ring = coords[0] if isinstance(coords[0], list) else []
        for lng, lat in (ring[:-1] if len(ring) >= 2 else []):
            yield float(lng), float(lat)

    elif t == "MultiPolygon" and isinstance(coords, list):
        for poly in coords:
            if not isinstance(poly, list) or not poly:
                continue
            ring = poly[0] if isinstance(poly[0], list) else []
            for lng, lat in (ring[:-1] if len(ring) >= 2 else []):
                yield float(lng), float(lat)


def polygon_is_on_land(geom: dict) -> bool:
    """
    True if ALL outer-ring points are on land.
    (sea check disabled => always True)
    Supports Polygon and MultiPolygon.
    """
    feats = load_land_geojson()
    if not feats:
        return True

    pts = list(iter_polygon_points(geom))
    if not pts:
        return False

    for lng, lat in pts:
        if not point_on_land(lng, lat):
            return False
    return True
