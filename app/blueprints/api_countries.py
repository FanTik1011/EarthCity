# app/blueprints/api_countries.py
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from ..extensions import db
from ..models import Country, Factory, CountryInventory, MarketOffer

from ..services.land import polygon_is_on_land
from ..services.geo import (
    polygon_area_km2_equirect,
    geom_intersects_any_country,
    geom_intersects_any_country_except,
)
from ..services.economy import (
    COUNTRY_MAX_AREA_KM2,
    COUNTRY_MAX_POINTS,
    COUNTRY_MIN_POINTS,
    compute_country_cost,
    market_price,
    RESOURCE_BASE_PRICES,
)
from ..services.resources import get_resource_nodes

# shapely for union-based expand attach
from shapely.geometry import shape, mapping
from shapely.ops import unary_union


bp_api_countries = Blueprint("api_countries", __name__)


# =========================================================
# Helpers
# =========================================================
def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _point_in_ring(lng: float, lat: float, ring: List[List[float]]) -> bool:
    """
    Ray casting point-in-polygon for one closed ring.
    ring: [[lng,lat], ...] with ring[0] == ring[-1]
    """
    if not ring or len(ring) < 4:
        return False

    inside = False
    n = len(ring) - 1
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat):
            x_int = (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi
            if lng < x_int:
                inside = not inside
        j = i
    return inside


def _country_outer_rings(country: Country) -> List[List[List[float]]]:
    """
    Return list of outer rings for Polygon or MultiPolygon stored in country.geom_json.
    Each ring is closed list [[lng,lat], ...] where first==last.
    """
    try:
        if not country.geom_json:
            return []
        geom = json.loads(country.geom_json)
    except Exception:
        return []

    if not isinstance(geom, dict):
        return []

    t = geom.get("type")
    coords = geom.get("coordinates")
    rings: List[List[List[float]]] = []

    if t == "Polygon" and isinstance(coords, list) and coords and isinstance(coords[0], list):
        rings.append(coords[0])
    elif t == "MultiPolygon" and isinstance(coords, list):
        for poly in coords:
            if isinstance(poly, list) and poly and isinstance(poly[0], list):
                rings.append(poly[0])

    out: List[List[List[float]]]= []
    for r in rings:
        if isinstance(r, list) and len(r) >= 4 and r[0] == r[-1]:
            out.append(r)
    return out


def _country_contains_point(country: Country, lng: float, lat: float) -> bool:
    rings = _country_outer_rings(country)
    if not rings:
        return False
    for ring in rings:
        try:
            if _point_in_ring(float(lng), float(lat), ring):
                return True
        except Exception:
            continue
    return False


def _require_my_country(cid: int) -> Optional[Country]:
    c = db.session.get(Country, cid)
    if not c:
        return None
    if c.owner_user_id != current_user.id:
        return None
    return c


def _inv_get_or_create(country_id: int, resource: str) -> CountryInventory:
    row = CountryInventory.query.filter_by(country_id=country_id, resource=resource).first()
    if row:
        return row
    row = CountryInventory(country_id=country_id, resource=resource, amount=0.0)
    db.session.add(row)
    return row


def _validate_polygon_like(geom: Dict[str, Any], allow_multi: bool = False):
    """
    Validate Polygon (and optionally MultiPolygon) GeoJSON.
    Enforce:
      - points count
      - closed ring
      - lng/lat ranges
    """
    if not isinstance(geom, dict):
        return False, "Geometry must be object"

    gtype = geom.get("type")
    if gtype not in ("Polygon", "MultiPolygon"):
        return False, "Only Polygon (or MultiPolygon) supported"
    if gtype == "MultiPolygon" and not allow_multi:
        return False, "Only Polygon supported"

    coords = geom.get("coordinates")
    if not isinstance(coords, list) or not coords:
        return False, "Geometry coordinates invalid"

    # outer ring (first polygon outer)
    if gtype == "Polygon":
        ring = coords[0] if coords and isinstance(coords[0], list) else None
    else:
        ring = coords[0][0] if coords and isinstance(coords[0], list) and coords[0] and isinstance(coords[0][0], list) else None

    if not isinstance(ring, list):
        return False, "Polygon ring invalid"

    if len(ring) < (COUNTRY_MIN_POINTS + 1):
        return False, f"Polygon ring must have {COUNTRY_MIN_POINTS + 1}+ points"
    if len(ring) > (COUNTRY_MAX_POINTS + 1):
        return False, f"Too many points (max {COUNTRY_MAX_POINTS})"

    for p in ring:
        if not isinstance(p, list) or len(p) != 2:
            return False, "Point must be [lng, lat]"
        lng, lat = p
        if not (_is_num(lng) and _is_num(lat)):
            return False, "lng/lat must be numbers"
        if lng < -180 or lng > 180 or lat < -90 or lat > 90:
            return False, "lng/lat out of range"

    if ring[0] != ring[-1]:
        return False, "Polygon ring must be closed (first==last)"

    return True, ""


def _load_country_geom(country: Country) -> Optional[Dict[str, Any]]:
    try:
        if not country.geom_json:
            return None
        return json.loads(country.geom_json)
    except Exception:
        return None


def _normalize_shapely_to_geojson(g):
    """
    Convert shapely geometry to GeoJSON dict; fix invalid via buffer(0).
    """
    if g is None:
        return None
    try:
        if not g.is_valid:
            g = g.buffer(0)
        if g.is_empty:
            return None
        gj = mapping(g)
        if gj.get("type") not in ("Polygon", "MultiPolygon"):
            return None
        return gj
    except Exception:
        return None


# =========================================================
# Countries public
# =========================================================
@bp_api_countries.get("/api/countries")
def api_countries_list():
    countries = Country.query.order_by(Country.created_at.asc()).all()
    fc = {"type": "FeatureCollection", "features": [c.to_feature() for c in countries]}
    return jsonify(ok=True, data=fc)


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


# =========================================================
# My country
# =========================================================
@bp_api_countries.get("/api/my/country")
@login_required
def api_my_country():
    if getattr(current_user, "is_blocked", False):
        return jsonify(ok=False, error="Blocked"), 403
    c = Country.query.filter_by(owner_user_id=current_user.id).first()
    if not c:
        return jsonify(ok=True, data=None)
    return jsonify(ok=True, data=c.to_feature())


# =========================================================
# CREATE country
# =========================================================
@bp_api_countries.post("/api/countries")
def api_countries_create():
    if not current_user.is_authenticated:
        return jsonify(ok=False, error="Not authenticated"), 401
    if getattr(current_user, "is_blocked", False):
        return jsonify(ok=False, error="Blocked"), 403
    if not current_user.is_confirmed:
        return jsonify(ok=False, error="Email not confirmed"), 403

    # one country per user
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
        geom_json=json.dumps(geom, ensure_ascii=False),
    )

    db.session.add(country)
    db.session.commit()

    return jsonify(ok=True, country=country.to_feature(), coins=int(current_user.coins or 0))


# =========================================================
# UPDATE geometry (redraw polygon)
# =========================================================
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


# =========================================================
# EXPAND attach (server unions base + drawn piece)
# =========================================================
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
    add_geom = data.get("geometry")

    ok, err = _validate_polygon_like(add_geom, allow_multi=False)
    if not ok:
        return jsonify(ok=False, error=err), 400

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

    # must touch (no remote islands)
    try:
        if not base_shape.buffer(0).intersects(add_shape.buffer(0)):
            return jsonify(ok=False, error="Цей шматок не прилягає до країни (має торкатись кордону)."), 400
    except Exception:
        pass

    merged = unary_union([base_shape, add_shape])
    merged_gj = _normalize_shapely_to_geojson(merged)
    if not merged_gj:
        return jsonify(ok=False, error="Union failed (invalid result)"), 400

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

    return jsonify(ok=True, country=c.to_feature(), coins=int(current_user.coins or 0), delta_cost=delta, merged_type=merged_gj.get("type"))


# =========================================================
# Inventory (shared for the country)
# =========================================================
@bp_api_countries.get("/api/countries/<int:cid>/inventory")
@login_required
def api_country_inventory(cid: int):
    if getattr(current_user, "is_blocked", False):
        return jsonify(ok=False, error="Blocked"), 403

    c = _require_my_country(cid)
    if not c:
        return jsonify(ok=False, error="Not your country"), 403

    rows = CountryInventory.query.filter_by(country_id=c.id).all()
    data = {r.resource: float(r.amount or 0.0) for r in rows}
    return jsonify(ok=True, data=data, country_id=c.id)


# =========================================================
# Harvest (nodes inside country -> inventory)
# =========================================================
@bp_api_countries.post("/api/countries/<int:cid>/harvest")
@login_required
def api_country_harvest(cid: int):
    if getattr(current_user, "is_blocked", False):
        return jsonify(ok=False, error="Blocked"), 403
    if not current_user.is_confirmed:
        return jsonify(ok=False, error="Email not confirmed"), 403

    c = _require_my_country(cid)
    if not c:
        return jsonify(ok=False, error="Not your country"), 403

    nodes = get_resource_nodes()

    # safe tuning defaults
    area = float(c.area_km2 or 0.0)
    area_factor = max(1.0, min(4.0, (area / 2500.0) ** 0.35))  # mild scaling
    base_per_node = 6.0  # per harvest call at strength=1.0

    gained: Dict[str, float] = {}
    inside_count = 0

    for n in nodes:
        lng = float(n["lng"])
        lat = float(n["lat"])
        if not _country_contains_point(c, lng, lat):
            continue

        inside_count += 1
        rtype = (n.get("type") or "unknown").strip()
        strength = float(n.get("strength", 0.5))

        amount = base_per_node * strength * area_factor
        inv = _inv_get_or_create(c.id, rtype)
        inv.amount = float(inv.amount or 0.0) + float(amount)

        gained[rtype] = float(gained.get(rtype, 0.0) + amount)

    db.session.commit()
    return jsonify(ok=True, gained=gained, nodes_inside=int(inside_count))


# =========================================================
# NPC Market buy/sell (system)
# =========================================================
@bp_api_countries.post("/api/market/sell")
@login_required
def api_market_sell():
    if getattr(current_user, "is_blocked", False):
        return jsonify(ok=False, error="Blocked"), 403
    if not current_user.is_confirmed:
        return jsonify(ok=False, error="Email not confirmed"), 403

    data = request.get_json(force=True, silent=True) or {}
    cid = int(data.get("country_id") or 0)
    resource = (data.get("resource") or "").strip()
    amount = float(data.get("amount") or 0)

    if cid <= 0 or not resource or amount <= 0:
        return jsonify(ok=False, error="country_id/resource/amount required"), 400

    c = _require_my_country(cid)
    if not c:
        return jsonify(ok=False, error="Not your country"), 403

    price = int(market_price(resource, "sell") or 0)
    if price <= 0:
        return jsonify(ok=False, error="Unknown resource"), 400

    inv = CountryInventory.query.filter_by(country_id=c.id, resource=resource).first()
    have = float(inv.amount or 0.0) if inv else 0.0
    if have + 1e-9 < amount:
        return jsonify(ok=False, error=f"Not enough {resource} in inventory"), 400

    inv.amount = have - amount
    coins_add = int(round(price * amount))
    current_user.coins = int(current_user.coins or 0) + coins_add

    db.session.commit()
    return jsonify(ok=True, sold={"resource": resource, "amount": amount, "price": price, "coins_add": coins_add}, coins=int(current_user.coins or 0))


@bp_api_countries.post("/api/market/buy")
@login_required
def api_market_buy():
    if getattr(current_user, "is_blocked", False):
        return jsonify(ok=False, error="Blocked"), 403
    if not current_user.is_confirmed:
        return jsonify(ok=False, error="Email not confirmed"), 403

    data = request.get_json(force=True, silent=True) or {}
    cid = int(data.get("country_id") or 0)
    resource = (data.get("resource") or "").strip()
    amount = float(data.get("amount") or 0)

    if cid <= 0 or not resource or amount <= 0:
        return jsonify(ok=False, error="country_id/resource/amount required"), 400

    c = _require_my_country(cid)
    if not c:
        return jsonify(ok=False, error="Not your country"), 403

    price = int(market_price(resource, "buy") or 0)
    if price <= 0:
        return jsonify(ok=False, error="Unknown resource"), 400

    cost = int(round(price * amount))
    if int(current_user.coins or 0) < cost:
        return jsonify(ok=False, error=f"Not enough coins. Need {cost} EC."), 400

    current_user.coins = int(current_user.coins or 0) - cost
    inv = _inv_get_or_create(c.id, resource)
    inv.amount = float(inv.amount or 0.0) + amount

    db.session.commit()
    return jsonify(ok=True, bought={"resource": resource, "amount": amount, "price": price, "cost": cost}, coins=int(current_user.coins or 0))


@bp_api_countries.get("/api/market/prices")
def api_market_prices():
    base = {k: int(v) for k, v in (RESOURCE_BASE_PRICES or {}).items()}
    out: Dict[str, Dict[str, int]] = {}
    for r in base.keys():
        out[r] = {
            "base": int(base[r]),
            "buy": int(market_price(r, "buy") or 0),
            "sell": int(market_price(r, "sell") or 0),
        }
    order = sorted(out.keys(), key=lambda x: out[x]["base"], reverse=True)
    return jsonify(ok=True, data=out, order=order)


# =========================================================
# P2P Market (player-to-player)
# =========================================================
@bp_api_countries.get("/api/p2p/offers")
def api_p2p_offers_list():
    resource = (request.args.get("resource") or "").strip()
    limit = int(request.args.get("limit") or 60)
    limit = max(1, min(limit, 200))

    q = MarketOffer.query.filter_by(is_active=True)
    if resource:
        q = q.filter(MarketOffer.resource == resource)

    offers = q.order_by(MarketOffer.created_at.desc()).limit(limit).all()
    return jsonify(ok=True, data=[o.to_dict() for o in offers])


@bp_api_countries.post("/api/p2p/offers")
@login_required
def api_p2p_offer_create():
    if getattr(current_user, "is_blocked", False):
        return jsonify(ok=False, error="Blocked"), 403
    if not current_user.is_confirmed:
        return jsonify(ok=False, error="Email not confirmed"), 403

    data = request.get_json(force=True, silent=True) or {}
    cid = int(data.get("country_id") or 0)
    resource = (data.get("resource") or "").strip()
    amount = float(data.get("amount") or 0)
    ppu = int(data.get("price_per_unit") or 0)

    if cid <= 0 or not resource or amount <= 0 or ppu <= 0:
        return jsonify(ok=False, error="country_id/resource/amount/price_per_unit required"), 400
    if amount > 1e9:
        return jsonify(ok=False, error="Amount too large"), 400
    if ppu > 10_000_000:
        return jsonify(ok=False, error="Price too large"), 400

    c = _require_my_country(cid)
    if not c:
        return jsonify(ok=False, error="Not your country"), 403

    inv = CountryInventory.query.filter_by(country_id=c.id, resource=resource).first()
    have = float(inv.amount or 0.0) if inv else 0.0
    if have + 1e-9 < amount:
        return jsonify(ok=False, error=f"Not enough {resource} in inventory"), 400

    # reserve
    inv.amount = have - amount

    offer = MarketOffer(
        seller_country_id=c.id,
        resource=resource,
        price_per_unit=int(ppu),
        amount_total=float(amount),
        amount_left=float(amount),
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db.session.add(offer)
    db.session.commit()

    return jsonify(ok=True, data=offer.to_dict())


@bp_api_countries.post("/api/p2p/offers/<int:offer_id>/buy")
@login_required
def api_p2p_offer_buy(offer_id: int):
    if getattr(current_user, "is_blocked", False):
        return jsonify(ok=False, error="Blocked"), 403
    if not current_user.is_confirmed:
        return jsonify(ok=False, error="Email not confirmed"), 403

    data = request.get_json(force=True, silent=True) or {}
    buyer_country_id = int(data.get("country_id") or 0)
    amount = float(data.get("amount") or 0)

    if buyer_country_id <= 0 or amount <= 0:
        return jsonify(ok=False, error="country_id/amount required"), 400

    buyer_country = _require_my_country(buyer_country_id)
    if not buyer_country:
        return jsonify(ok=False, error="Not your country"), 403

    offer = db.session.get(MarketOffer, offer_id)
    if not offer or not offer.is_active:
        return jsonify(ok=False, error="Offer not found"), 404

    if int(offer.seller_country_id) == int(buyer_country.id):
        return jsonify(ok=False, error="You can't buy your own offer"), 400

    left = float(offer.amount_left or 0.0)
    if left + 1e-9 < amount:
        return jsonify(ok=False, error="Not enough amount left"), 400

    total_cost = int(round(int(offer.price_per_unit) * float(amount)))
    if int(current_user.coins or 0) < total_cost:
        return jsonify(ok=False, error=f"Not enough coins. Need {total_cost} EC."), 400

    seller_country = db.session.get(Country, int(offer.seller_country_id))
    if not seller_country or not seller_country.owner:
        return jsonify(ok=False, error="Seller missing"), 400

    # coins transfer
    current_user.coins = int(current_user.coins or 0) - total_cost
    seller_country.owner.coins = int(seller_country.owner.coins or 0) + total_cost

    # inventory add to buyer
    inv_b = _inv_get_or_create(buyer_country.id, offer.resource)
    inv_b.amount = float(inv_b.amount or 0.0) + float(amount)

    # reduce offer
    offer.amount_left = left - amount
    if offer.amount_left <= 1e-9:
        offer.amount_left = 0.0
        offer.is_active = False

    db.session.commit()

    return jsonify(ok=True, data={
        "offer_id": int(offer.id),
        "resource": offer.resource,
        "bought": float(amount),
        "price_per_unit": int(offer.price_per_unit),
        "total_cost": int(total_cost),
        "buyer_coins": int(current_user.coins or 0),
        "offer_left": float(offer.amount_left or 0.0),
        "offer_active": bool(offer.is_active),
    })


@bp_api_countries.post("/api/p2p/offers/<int:offer_id>/cancel")
@login_required
def api_p2p_offer_cancel(offer_id: int):
    if getattr(current_user, "is_blocked", False):
        return jsonify(ok=False, error="Blocked"), 403

    offer = db.session.get(MarketOffer, offer_id)
    if not offer or not offer.is_active:
        return jsonify(ok=False, error="Offer not found"), 404

    seller_country = _require_my_country(int(offer.seller_country_id))
    if not seller_country:
        return jsonify(ok=False, error="Not your offer"), 403

    left = float(offer.amount_left or 0.0)
    if left > 0:
        inv = _inv_get_or_create(seller_country.id, offer.resource)
        inv.amount = float(inv.amount or 0.0) + left

    offer.amount_left = 0.0
    offer.is_active = False

    db.session.commit()
    return jsonify(ok=True, data=offer.to_dict())
