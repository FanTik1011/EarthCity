# api_countries.py
import json
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from ..extensions import db
from ..models import Country, Factory

from ..services.land import polygon_is_on_land
from ..services.geo import (
    polygon_area_km2_equirect,
    geom_intersects_any_country,
    geom_intersects_any_country_except,
)
from ..services.economy import (
    COUNTRY_MAX_AREA_KM2, COUNTRY_MAX_POINTS, COUNTRY_MIN_POINTS,
    compute_country_cost
)

# ✅ NEW: Shapely for union (attach territory)
from shapely.geometry import shape, mapping
from shapely.ops import unary_union


bp_api_countries = Blueprint("api_countries", __name__)


# -----------------------------
# Geometry helpers
# -----------------------------
def _is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)

def _validate_polygon_like(geom: dict, *, allow_multi: bool = False):
    """
    Validates GeoJSON Polygon (and optionally MultiPolygon).
    Ensures:
      - type is Polygon (or MultiPolygon if allow_multi)
      - first ring is closed
      - lng/lat valid
      - point count within limits (per ring; we focus on outer ring)
    """
    if not isinstance(geom, dict):
        return False, "Geometry must be object"

    gtype = geom.get("type")
    if gtype not in ("Polygon", "MultiPolygon"):
        return False, "Only Polygon (or MultiPolygon) supported"

    if gtype == "MultiPolygon" and not allow_multi:
        return False, "Only Polygon supported"

    coords = geom.get("coordinates")
    if not isinstance(coords, list) or len(coords) < 1:
        return False, "Geometry coordinates invalid"

    # Take outer ring of first polygon (enough for point-limit and basic validation)
    if gtype == "Polygon":
        ring = coords[0] if coords and isinstance(coords[0], list) else None
    else:
        # MultiPolygon: coords[0][0] = first poly first ring
        ring = coords[0][0] if coords and isinstance(coords[0], list) and coords[0] and isinstance(coords[0][0], list) else None

    if not isinstance(ring, list) or len(ring) < (COUNTRY_MIN_POINTS + 1):
        return False, f"Polygon ring must have {COUNTRY_MIN_POINTS+1}+ points"

    if len(ring) > (COUNTRY_MAX_POINTS + 1):
        return False, f"Too many points (max {COUNTRY_MAX_POINTS})"

    for p in ring:
        if (not isinstance(p, list)) or len(p) != 2:
            return False, "Point must be [lng, lat]"
        lng, lat = p
        if not (_is_num(lng) and _is_num(lat)):
            return False, "lng/lat must be numbers"
        if lng < -180 or lng > 180 or lat < -90 or lat > 90:
            return False, "lng/lat out of range"

    if ring[0] != ring[-1]:
        return False, "Polygon ring must be closed (first==last)"

    return True, ""


def _load_country_geom(country: Country) -> dict | None:
    try:
        if not country.geom_json:
            return None
        return json.loads(country.geom_json)
    except Exception:
        return None


def _normalize_shapely_to_geojson(g):
    """
    Convert shapely geometry to GeoJSON dict.
    - Fix invalid geometry via buffer(0)
    - Return Polygon or MultiPolygon (we allow multi on expand)
    """
    if g is None:
        return None

    if not g.is_valid:
        g = g.buffer(0)

    if g.is_empty:
        return None

    # mapping() -> GeoJSON-like dict
    gj = mapping(g)

    # We only accept Polygon/MultiPolygon for storage
    if gj.get("type") not in ("Polygon", "MultiPolygon"):
        return None

    return gj


# -----------------------------
# Routes
# -----------------------------
@bp_api_countries.get("/api/countries")
def api_countries_list():
    countries = Country.query.order_by(Country.created_at.asc()).all()
    fc = {"type": "FeatureCollection", "features": [c.to_feature() for c in countries]}
    return jsonify(ok=True, data=fc)


@bp_api_countries.post("/api/countries")
def api_countries_create():
    if not current_user.is_authenticated:
        return jsonify(ok=False, error="Not authenticated"), 401
    if not current_user.is_confirmed:
        return jsonify(ok=False, error="Email not confirmed"), 403
    if getattr(current_user, "is_blocked", False):
        return jsonify(ok=False, error="Blocked"), 403

    if Country.query.filter_by(owner_user_id=current_user.id).first():
        return jsonify(ok=False, error="Ти вже маєш країну. 1 акаунт = 1 країна."), 409

    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    color = (data.get("color") or "#7c3aed").strip()
    geom = data.get("geometry")

    if len(name) < 2:
        return jsonify(ok=False, error="Name мінімум 2 символи."), 400
    if not color.startswith("#") or len(color) not in (4, 7):
        return jsonify(ok=False, error="Invalid color."), 400

    ok, err = _validate_polygon_like(geom, allow_multi=False)
    if not ok:
        return jsonify(ok=False, error=err), 400

    if not polygon_is_on_land(geom):
        return jsonify(ok=False, error="Країну можна створювати лише на суші (не на морі/океані)."), 400

    if geom_intersects_any_country(geom):
        return jsonify(ok=False, error="Не можна створювати країну на країні (перетин з іншою країною)."), 400

    area_km2 = polygon_area_km2_equirect(geom)
    if area_km2 > COUNTRY_MAX_AREA_KM2:
        return jsonify(ok=False, error=f"Країна занадто велика: {int(area_km2):,} км² (макс {COUNTRY_MAX_AREA_KM2:,} км²)"), 400

    cost = compute_country_cost(area_km2)
    if int(current_user.coins or 0) < cost:
        return jsonify(ok=False, error=f"Недостатньо монет. Треба {cost} EC, у тебе {int(current_user.coins or 0)} EC."), 400

    current_user.coins = int(current_user.coins or 0) - cost

    country = Country(
        owner_user_id=current_user.id,
        name=name[:120],
        color=color,
        area_km2=float(area_km2),
        create_cost=int(cost),
        geom_json=json.dumps(geom, ensure_ascii=False)
    )
    db.session.add(country)
    db.session.commit()

    return jsonify(ok=True, country=country.to_feature(), coins=int(current_user.coins or 0))


@bp_api_countries.get("/api/my/country")
@login_required
def api_my_country():
    if getattr(current_user, "is_blocked", False):
        return jsonify(ok=False, error="Blocked"), 403
    c = Country.query.filter_by(owner_user_id=current_user.id).first()
    if not c:
        return jsonify(ok=True, data=None)
    return jsonify(ok=True, data=c.to_feature())


# ✅ OLD endpoint stays: redraw whole polygon (works)
@bp_api_countries.post("/api/countries/<int:cid>/update-geometry")
@login_required
def api_country_update_geometry(cid: int):
    if getattr(current_user, "is_blocked", False):
        return jsonify(ok=False, error="Blocked"), 403
    if not current_user.is_confirmed:
        return jsonify(ok=False, error="Email not confirmed"), 403

    c = db.session.get(Country, cid)
    if not c:
        return jsonify(ok=False, error="Country not found"), 404
    if c.owner_user_id != current_user.id:
        return jsonify(ok=False, error="Not your country"), 403

    data = request.get_json(force=True, silent=True) or {}
    geom = data.get("geometry")

    ok, err = _validate_polygon_like(geom, allow_multi=False)
    if not ok:
        return jsonify(ok=False, error=err), 400

    if not polygon_is_on_land(geom):
        return jsonify(ok=False, error="Країну можна тримати лише на суші (не на морі/океані)."), 400

    if geom_intersects_any_country_except(geom, exclude_country_id=c.id):
        return jsonify(ok=False, error="Не можна розширити на іншу країну (перетин)."), 400

    new_area = polygon_area_km2_equirect(geom)
    if new_area > COUNTRY_MAX_AREA_KM2:
        return jsonify(ok=False, error=f"Занадто велика: {int(new_area):,} км² (макс {COUNTRY_MAX_AREA_KM2:,} км²)"), 400

    old_area = float(c.area_km2 or 0.0)

    old_cost = compute_country_cost(old_area)
    new_cost = compute_country_cost(new_area)
    delta = int(new_cost - old_cost)

    if delta > 0:
        if int(current_user.coins or 0) < delta:
            return jsonify(ok=False, error=f"Недостатньо монет. Треба {delta} EC (за розширення)."), 400
        current_user.coins = int(current_user.coins or 0) - delta

    c.geom_json = json.dumps(geom, ensure_ascii=False)
    c.area_km2 = float(new_area)

    db.session.commit()
    return jsonify(ok=True, country=c.to_feature(), coins=int(current_user.coins or 0), delta_cost=delta)


# ✅ NEW: attach territory (union)
# Client draws ONLY the area to add. Server unions it with existing geometry.
@bp_api_countries.post("/api/countries/<int:cid>/expand-attach")
@login_required
def api_country_expand_attach(cid: int):
    if getattr(current_user, "is_blocked", False):
        return jsonify(ok=False, error="Blocked"), 403
    if not current_user.is_confirmed:
        return jsonify(ok=False, error="Email not confirmed"), 403

    c = db.session.get(Country, cid)
    if not c:
        return jsonify(ok=False, error="Country not found"), 404
    if c.owner_user_id != current_user.id:
        return jsonify(ok=False, error="Not your country"), 403

    data = request.get_json(force=True, silent=True) or {}
    add_geom = data.get("geometry")  # polygon user drew to attach

    ok, err = _validate_polygon_like(add_geom, allow_multi=False)
    if not ok:
        return jsonify(ok=False, error=err), 400

    # Land check for the ADD piece (strict)
    if not polygon_is_on_land(add_geom):
        return jsonify(ok=False, error="Додавати можна лише сушу (не море/океан)."), 400

    base_geom = _load_country_geom(c)
    if not base_geom:
        return jsonify(ok=False, error="Country geometry broken"), 500

    try:
        base_shape = shape(base_geom)
        add_shape = shape(add_geom)
    except Exception:
        return jsonify(ok=False, error="Invalid geometry (shape parse)"), 400

    if base_shape.is_empty or add_shape.is_empty:
        return jsonify(ok=False, error="Empty geometry"), 400

    # ✅ union (attach)
    merged = unary_union([base_shape, add_shape])
    merged_gj = _normalize_shapely_to_geojson(merged)
    if not merged_gj:
        return jsonify(ok=False, error="Union failed (invalid result)"), 400

    # Optionally: reject if the new part doesn't touch (so you cannot create islands)
    # If you want to allow islands — comment this out.
    try:
        if not base_shape.buffer(0).intersects(add_shape.buffer(0)):
            return jsonify(ok=False, error="Цей шматок не прилягає до країни (має торкатись кордону)."), 400
    except Exception:
        pass

    # Now server-side checks for merged geometry
    if not polygon_is_on_land(merged_gj):
        return jsonify(ok=False, error="Після об'єднання країна виходить у море/океан."), 400

    if geom_intersects_any_country_except(merged_gj, exclude_country_id=c.id):
        return jsonify(ok=False, error="Після доєднання є перетин з іншою країною."), 400

    new_area = polygon_area_km2_equirect(merged_gj)
    if new_area > COUNTRY_MAX_AREA_KM2:
        return jsonify(ok=False, error=f"Занадто велика: {int(new_area):,} км² (макс {COUNTRY_MAX_AREA_KM2:,} км²)"), 400

    old_area = float(c.area_km2 or 0.0)
    old_cost = compute_country_cost(old_area)
    new_cost = compute_country_cost(new_area)
    delta = int(new_cost - old_cost)

    if delta > 0:
        if int(current_user.coins or 0) < delta:
            return jsonify(ok=False, error=f"Недостатньо монет. Треба {delta} EC (за доєднання)."), 400
        current_user.coins = int(current_user.coins or 0) - delta

    c.geom_json = json.dumps(merged_gj, ensure_ascii=False)
    c.area_km2 = float(new_area)
    db.session.commit()

    return jsonify(
        ok=True,
        country=c.to_feature(),
        coins=int(current_user.coins or 0),
        delta_cost=delta,
        merged_type=merged_gj.get("type"),
    )


@bp_api_countries.get("/api/countries/<int:cid>")
def api_country_details(cid: int):
    c = db.session.get(Country, cid)
    if not c:
        return jsonify(ok=False, error="Country not found"), 404

    factories_count = Factory.query.filter_by(country_id=c.id).count()
    is_mine = False
    if current_user.is_authenticated:
        is_mine = (c.owner_user_id == current_user.id)

    return jsonify(ok=True, data={
        "id": c.id,
        "name": c.name,
        "color": c.color,
        "area_km2": float(c.area_km2 or 0),
        "factories": int(factories_count),
        "owner_username": (c.owner.username if c.owner else "unknown"),
        "is_mine": bool(is_mine),
    })
