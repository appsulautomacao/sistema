from flask import Blueprint, jsonify
from flask_login import login_required, current_user
from core.metrics import get_sector_routing_analytics_map
from core.presence import get_company_presence_map
from models import Sector, User, Conversation

api_sectors_bp = Blueprint("api_sectors", __name__, url_prefix="/api")


@api_sectors_bp.route("/sectors")
@login_required
def get_sectors():
    sectors = Sector.query.filter_by(
        company_id=current_user.company_id
    ).all()

    return jsonify([
        {"id": s.id, "name": s.name}
        for s in sectors
    ])

@api_sectors_bp.route("/sectors/overview")
@login_required
def sectors_overview():

    sectors = Sector.query.filter_by(
        company_id=current_user.company_id
    ).all()
    presence_map = get_company_presence_map(current_user.company_id)
    analytics_map = get_sector_routing_analytics_map(current_user.company_id)

    result = []

    for s in sectors:
        users = User.query.filter_by(
            sector_id=s.id,
            company_id=current_user.company_id
        ).all()

        conversations = Conversation.query.filter_by(
            current_sector_id=s.id,
            company_id=current_user.company_id
        ).all()

        analytics = analytics_map.get(s.id, {})

        result.append({
            "id": s.id,
            "name": s.name,
            "is_central": s.is_central,
            "users": [u.name for u in users],
            "users_detail": [
                {
                    "id": u.id,
                    "name": u.name,
                    "status": presence_map.get(u.id, "offline"),
                }
                for u in users
            ],
            "online": len([u for u in users if presence_map.get(u.id) == "online"]),
            "away": len([u for u in users if presence_map.get(u.id) == "away"]),
            "offline": len([u for u in users if presence_map.get(u.id, "offline") == "offline"]),
            "total": len(conversations),
            "unassigned": len([c for c in conversations if not c.assigned_to]),
            "assigned": len([c for c in conversations if c.assigned_to]),
            "routing_metrics": {
                "total_routings": analytics.get("total_routings", 0),
                "completed_routings": analytics.get("completed_routings", 0),
                "open_routings": analytics.get("open_routings", 0),
                "inbound_handoffs": analytics.get("inbound_handoffs", 0),
                "average_routing_minutes": analytics.get("average_routing_minutes"),
                "average_open_minutes": analytics.get("average_open_minutes"),
                "longest_open_minutes": analytics.get("longest_open_minutes"),
                "attention_level": analytics.get("attention_level", "ok"),
            }
        })

    return jsonify(result)
