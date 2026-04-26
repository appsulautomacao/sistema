from flask import Blueprint, jsonify
from flask_login import current_user, login_required

from core.presence import get_company_presence_map
from models import CompanySettings, Sector


dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/api/me")
@login_required
def me():
    sector_name = None
    settings = CompanySettings.query.filter_by(company_id=current_user.company_id).first()

    if current_user.sector_id:
        sector = Sector.query.get(current_user.sector_id)
        if sector:
            sector_name = sector.name

    presence_status = get_company_presence_map(current_user.company_id).get(
        current_user.id,
        "offline",
    )

    return jsonify({
        "name": current_user.name,
        "sector": sector_name,
        "status": presence_status,
        "role": current_user.role,
        "company_name": current_user.company.name if current_user.company else None,
        "company_slug": current_user.company.slug if current_user.company else None,
        "logo_url": current_user.company.logo_url if current_user.company else None,
        "primary_color": current_user.company.primary_color if current_user.company else None,
        "ai_enabled": bool(settings.central_ai_enabled) if settings else False,
    })
