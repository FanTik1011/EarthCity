import json
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from models import db
from models.city import City
from models.city_mayor import CityMayor
from models.audit_log import AuditLog

city_rules_bp = Blueprint("city_rules_bp", __name__)

def is_mayor(city_id: int) -> bool:
    m = CityMayor.query.filter_by(city_id=city_id).first()
    return bool(m and m.user_id == current_user.id)

@city_rules_bp.get("/api/cities/<int:city_id>/rules")
def get_rules(city_id: int):
    city = City.query.get_or_404(city_id)
    m = CityMayor.query.filter_by(city_id=city_id).first()
    return jsonify({
        "city_id": city.id,
        "tax_percent": city.tax_percent,
        "budget": city.budget,
        "mayor_user_id": m.user_id if m else None
    })

@city_rules_bp.post("/api/cities/<int:city_id>/rules")
@login_required
def update_rules(city_id: int):
    if not is_mayor(city_id):
        return jsonify({"error": "only mayor can change rules"}), 403

    city = City.query.get_or_404(city_id)
    data = request.get_json(force=True, silent=True) or {}

    tax = data.get("tax_percent")
    if tax is None:
        return jsonify({"error": "tax_percent required"}), 400

    try:
        tax = int(tax)
    except ValueError:
        return jsonify({"error": "tax_percent must be integer"}), 400

    if tax < 0 or tax > 50:
        return jsonify({"error": "tax_percent must be between 0 and 50"}), 400

    old_tax = city.tax_percent
    city.tax_percent = tax

    db.session.add(AuditLog(
        actor_user_id=current_user.id,
        entity_type="city",
        entity_id=city_id,
        action="tax_changed",
        payload_json=json.dumps({"old": old_tax, "new": tax}, ensure_ascii=False)
    ))

    db.session.commit()
    return jsonify({"ok": True, "city_id": city_id, "tax_percent": city.tax_percent})
