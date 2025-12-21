import math
import json

def rad(d: float) -> float:
    return d * math.pi / 180.0

def haversine_km(lng1, lat1, lng2, lat2) -> float:
    R = 6371.0088
    dlat = rad(lat2 - lat1)
    dlng = rad(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rad(lat1)) * math.cos(rad(lat2)) * math.sin(dlng / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def point_in_polygon(lng: float, lat: float, ring) -> bool:
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

def polygon_area_km2_equirect(geom: dict) -> float:
    R = 6371.0088
    ring = geom["coordinates"][0]
    pts = ring[:-1]
    if len(pts) < 3:
        return 0.0

    lat0 = sum(p[1] for p in pts) / len(pts)
    lat0r = rad(lat0)

    xy = []
    for lng, lat in pts:
        x = R * rad(lng) * math.cos(lat0r)
        y = R * rad(lat)
        xy.append((x, y))

    s = 0.0
    for i in range(len(xy)):
        x1, y1 = xy[i]
        x2, y2 = xy[(i + 1) % len(xy)]
        s += x1 * y2 - x2 * y1

    return abs(s) / 2.0

def country_polygon_ring(geom_json: str):
    try:
        geom = json.loads(geom_json)
        return geom["coordinates"][0]
    except Exception:
        return None
