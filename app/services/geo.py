# services/geo.py
import math
import json
from shapely.geometry import shape
from shapely.ops import transform
from ..models import Country

R_EARTH_KM = 6371.0088

def rad(d: float) -> float:
    return d * math.pi / 180.0

def haversine_km(lng1, lat1, lng2, lat2) -> float:
    R = R_EARTH_KM
    dlat = rad(lat2 - lat1)
    dlng = rad(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rad(lat1)) * math.cos(rad(lat2)) * math.sin(dlng / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


# -----------------------
# Area (Polygon/MultiPolygon)
# -----------------------
def _equirect_project(lng, lat, lat0r):
    # returns km in equirect projection
    x = R_EARTH_KM * rad(lng) * math.cos(lat0r)
    y = R_EARTH_KM * rad(lat)
    return (x, y)

def _area_km2_of_polygon_coords(poly_coords) -> float:
    """
    poly_coords = [outer_ring, hole1, hole2, ...]
    Each ring is [ [lng,lat], ... closed ... ]
    Uses equirect approximation around centroid latitude.
    """
    outer = poly_coords[0]
    pts = outer[:-1]
    if len(pts) < 3:
        return 0.0

    lat0 = sum(p[1] for p in pts) / len(pts)
    lat0r = rad(lat0)

    def ring_area(ring):
        pts2 = ring[:-1]
        if len(pts2) < 3:
            return 0.0
        xy = [_equirect_project(lng, lat, lat0r) for (lng, lat) in pts2]
        s = 0.0
        for i in range(len(xy)):
            x1, y1 = xy[i]
            x2, y2 = xy[(i + 1) % len(xy)]
            s += x1 * y2 - x2 * y1
        return abs(s) / 2.0

    outer_area = ring_area(poly_coords[0])
    holes_area = 0.0
    for hole in poly_coords[1:]:
        holes_area += ring_area(hole)

    return max(0.0, outer_area - holes_area)

def polygon_area_km2_equirect(geom: dict) -> float:
    """
    Accepts GeoJSON Polygon OR MultiPolygon.
    Returns area in km² using equirect approximation.
    """
    if not isinstance(geom, dict):
        return 0.0
    t = geom.get("type")
    coords = geom.get("coordinates")
    if t == "Polygon" and isinstance(coords, list) and coords:
        return _area_km2_of_polygon_coords(coords)
    if t == "MultiPolygon" and isinstance(coords, list):
        total = 0.0
        for poly in coords:
            if isinstance(poly, list) and poly:
                total += _area_km2_of_polygon_coords(poly)
        return total
    return 0.0


# -----------------------
# Intersections (Shapely)
# -----------------------
def _safe_shape(geom: dict):
    """
    Parse geojson -> shapely geometry.
    Fix invalid geometry via buffer(0) if needed.
    """
    try:
        g = shape(geom)
    except Exception:
        return None
    if g.is_empty:
        return None
    if not g.is_valid:
        g = g.buffer(0)
        if g.is_empty:
            return None
    return g

def geom_intersects_any_country(new_geom: dict) -> bool:
    gnew = _safe_shape(new_geom)
    if gnew is None:
        return False

    for c in Country.query.all():
        try:
            old_geom = json.loads(c.geom_json)
        except Exception:
            continue
        gold = _safe_shape(old_geom)
        if gold is None:
            continue
        # intersects = touching counts as conflict (like your old code)
        if gnew.intersects(gold):
            return True
    return False

def geom_intersects_any_country_except(new_geom: dict, exclude_country_id: int) -> bool:
    gnew = _safe_shape(new_geom)
    if gnew is None:
        return False

    for c in Country.query.all():
        if int(c.id) == int(exclude_country_id):
            continue
        try:
            old_geom = json.loads(c.geom_json)
        except Exception:
            continue
        gold = _safe_shape(old_geom)
        if gold is None:
            continue
        if gnew.intersects(gold):
            return True
    return False
def point_in_polygon(lng: float, lat: float, ring) -> bool:
    """
    Backward-compatible helper (ray casting).
    `ring` is closed: [[lng,lat], ... , [lng,lat]].
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
