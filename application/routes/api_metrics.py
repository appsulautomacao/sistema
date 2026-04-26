from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from core.metrics import (
    get_average_first_response_by_agent,
    get_first_response_time,
    get_sector_handoff_analytics,
    get_sector_routing_analytics,
)
from models import Conversation, CompanySettings
from db import db

api_metrics_bp = Blueprint("api_metrics", __name__, url_prefix="/api")


@api_metrics_bp.route("/metrics/average-first-response")
@login_required
def average_first_response():
    data = get_average_first_response_by_agent(current_user.company_id)
    return jsonify(data)


@api_metrics_bp.route("/metrics/sectors/routing")
@login_required
def sector_routing_metrics():
    data = get_sector_routing_analytics(current_user.company_id)
    return jsonify(data)


@api_metrics_bp.route("/metrics/sectors/handoffs")
@login_required
def sector_handoff_metrics():
    data = get_sector_handoff_analytics(current_user.company_id)
    return jsonify(data)


@api_metrics_bp.route("/central/ai", methods=["POST"])
@login_required
def toggle_central_ai():
    enabled = request.json.get("enabled", False)

    settings = CompanySettings.query.filter_by(
        company_id=current_user.company_id
    ).first()

    if not settings:
        settings = CompanySettings(
            company_id=current_user.company_id,
        )
        db.session.add(settings)

    settings.central_ai_enabled = enabled
    db.session.commit()

    return {"status": "ok"}
