from flask import Blueprint, request, jsonify
from models.city import City
from services.geo_query import limit_for_zoom

map_bp = Blueprint("map_bp", __name__)

@map_bp.get("/api/cities")
def get_cities_in_bbox():
    bbox = request.args.get("bbox", "").strip()
    zoom_str = request.args.get("zoom", "6").strip()

    if not bbox:
        return jsonify({"zoom": 0, "limit": 0, "count": 0, "cities": []})

    try:
        zoom = int(float(zoom_str))
    except ValueError:
        zoom = 6

    parts = bbox.split(",")
    if len(parts) != 4:
        return jsonify({"error": "bbox must have 4 values"}), 400

    min_lng, min_lat, max_lng, max_lat = [float(x) for x in parts]
    lim = limit_for_zoom(zoom)

    cities = (City.query
        .filter(City.lat >= min_lat, City.lat <= max_lat)
        .filter(City.lng >= min_lng, City.lng <= max_lng)
        .limit(lim)
        .all())

    return jsonify({
        "zoom": zoom,
        "limit": lim,
        "count": len(cities),
        "cities": [c.to_marker_json() for c in cities]
    })
