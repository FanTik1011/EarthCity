import math
import json
from ..models import Country

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

def _orient(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

def _on_segment(a, b, c):
    return (min(a[0], b[0]) <= c[0] <= max(a[0], b[0]) and
            min(a[1], b[1]) <= c[1] <= max(a[1], b[1]))

def _segments_intersect(p1, p2, q1, q2) -> bool:
    o1 = _orient(p1, p2, q1)
    o2 = _orient(p1, p2, q2)
    o3 = _orient(q1, q2, p1)
    o4 = _orient(q1, q2, p2)

    if (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0):
        return True

    eps = 1e-12
    if abs(o1) < eps and _on_segment(p1, p2, q1): return True
    if abs(o2) < eps and _on_segment(p1, p2, q2): return True
    if abs(o3) < eps and _on_segment(q1, q2, p1): return True
    if abs(o4) < eps and _on_segment(q1, q2, p2): return True

    return False

def rings_intersect(ringA, ringB) -> bool:
    """
    True if polygons overlap/touch:
    - any edge intersects
    - or A contains a vertex of B
    - or B contains a vertex of A
    """
    if not ringA or not ringB:
        return False

    A = ringA[:-1]
    B = ringB[:-1]
    if len(A) < 3 or len(B) < 3:
        return False

    for i in range(len(A)):
        p1 = A[i]
        p2 = A[(i + 1) % len(A)]
        for j in range(len(B)):
            q1 = B[j]
            q2 = B[(j + 1) % len(B)]
            if _segments_intersect(p1, p2, q1, q2):
                return True

    if point_in_polygon(B[0][0], B[0][1], ringA):
        return True
    if point_in_polygon(A[0][0], A[0][1], ringB):
        return True

    return False

def geom_intersects_any_country(new_geom: dict) -> bool:
    new_ring = (new_geom.get("coordinates") or [[]])[0]
    if not new_ring:
        return False

    for c in Country.query.all():
        try:
            old_geom = json.loads(c.geom_json)
            old_ring = (old_geom.get("coordinates") or [[]])[0]
        except Exception:
            continue
        if rings_intersect(new_ring, old_ring):
            return True
    return False

def geom_intersects_any_country_except(new_geom: dict, exclude_country_id: int) -> bool:
    new_ring = (new_geom.get("coordinates") or [[]])[0]
    if not new_ring:
        return False

    for c in Country.query.all():
        if int(c.id) == int(exclude_country_id):
            continue
        try:
            old_geom = json.loads(c.geom_json)
            old_ring = (old_geom.get("coordinates") or [[]])[0]
        except Exception:
            continue
        if rings_intersect(new_ring, old_ring):
            return True
    return False
