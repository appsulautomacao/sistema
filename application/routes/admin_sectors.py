from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError

from db import db
from models import CompanySettings, Conversation, Sector, User

admin_sectors_bp = Blueprint(
    "admin_sectors",
    __name__,
    url_prefix="/admin/sectors"
)


@admin_sectors_bp.route("/")
@login_required
def list_sectors():
    if current_user.role != "ADMIN":
        return "Acesso negado", 403

    sectors = Sector.query.filter_by(
        company_id=current_user.company_id
    ).order_by(Sector.id.asc()).all()

    return render_template(
        "admin/sectors.html",
        sectors=sectors
    )


@admin_sectors_bp.route("/create", methods=["POST"])
@login_required
def create_sector():
    if current_user.role != "ADMIN":
        return "Acesso negado", 403

    name = (request.form.get("name") or "").strip()
    sla_minutes_raw = (request.form.get("sla_minutes") or "").strip()

    if not name:
        flash("Informe o nome do setor.", "warning")
        return redirect(url_for("admin_sectors.list_sectors"))

    existing_sector = Sector.query.filter(
        Sector.company_id == current_user.company_id,
        func.lower(Sector.name) == name.lower()
    ).first()
    if existing_sector:
        flash("Ja existe um setor com esse nome.", "warning")
        return redirect(url_for("admin_sectors.list_sectors"))

    is_central = name.lower() == "central"
    sla_minutes = int(sla_minutes_raw) if sla_minutes_raw.isdigit() else None

    sector = Sector(
        name=name,
        sla_minutes=sla_minutes,
        company_id=current_user.company_id,
        is_central=is_central,
    )
    db.session.add(sector)
    db.session.flush()

    if is_central:
        settings = CompanySettings.query.filter_by(
            company_id=current_user.company_id
        ).first()
        if not settings:
            settings = CompanySettings(company_id=current_user.company_id)
            db.session.add(settings)
        settings.central_sector_id = sector.id

    db.session.commit()
    flash("Setor criado com sucesso.", "success")
    return redirect(url_for("admin_sectors.list_sectors"))


@admin_sectors_bp.route("/delete/<int:sector_id>")
@login_required
def delete_sector(sector_id):
    if current_user.role != "ADMIN":
        return "Acesso negado", 403

    sector = Sector.query.get_or_404(sector_id)

    if sector.company_id != current_user.company_id:
        return "Acesso negado", 403

    if sector.is_central:
        flash("O setor Central e obrigatorio e nao pode ser excluido.", "warning")
        return redirect(url_for("admin_sectors.list_sectors"))

    has_users = User.query.filter_by(
        company_id=current_user.company_id,
        sector_id=sector.id
    ).first()
    if has_users:
        flash("Nao e possivel excluir setor que possui usuarios.", "warning")
        return redirect(url_for("admin_sectors.list_sectors"))

    has_conversations = Conversation.query.filter(
        Conversation.company_id == current_user.company_id,
        or_(
            Conversation.sector_id == sector.id,
            Conversation.current_sector_id == sector.id,
        )
    ).first()
    if has_conversations:
        flash("Nao e possivel excluir setor que possui conversas.", "warning")
        return redirect(url_for("admin_sectors.list_sectors"))

    settings = CompanySettings.query.filter_by(
        company_id=current_user.company_id
    ).first()
    if settings and settings.central_sector_id == sector.id:
        flash("Este setor esta definido como central e nao pode ser excluido.", "warning")
        return redirect(url_for("admin_sectors.list_sectors"))

    try:
        db.session.delete(sector)
        db.session.commit()
        flash("Setor excluido com sucesso.", "success")
    except IntegrityError:
        db.session.rollback()
        flash("Nao foi possivel excluir este setor por dependencia interna.", "warning")

    return redirect(url_for("admin_sectors.list_sectors"))
