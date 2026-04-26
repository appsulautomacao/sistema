from db import db
from core.routing import ensure_conversation_routing
from core.sla import start_sla_for_conversation
from core.history import log_conversation_event

from models import Company, CompanySettings, Conversation, Sector


def get_or_create_conversation(client_phone, client_name, company_id=None):
    filters = {"client_phone": client_phone}
    if company_id is not None:
        filters["company_id"] = company_id

    conversation = Conversation.query.filter_by(**filters).first()
    if conversation:
        return conversation

    # 🔥 pega empresa padrão (temporário até multiempresa real por token)
    company = db.session.get(Company, company_id) if company_id else Company.query.first()
    if not company:
        raise ValueError("Nenhuma empresa encontrada para criar a conversa")

    settings = CompanySettings.query.filter_by(company_id=company.id).first()
    central_sector_id = settings.central_sector_id if settings else None
    if not central_sector_id:
        central_sector = Sector.query.filter_by(
            company_id=company.id,
            is_central=True
        ).order_by(Sector.id.asc()).first()
        central_sector_id = central_sector.id if central_sector else None

    conversation = Conversation(
        client_phone=client_phone,
        client_name=client_name,
        status="new",
        company_id=company.id,
        sector_id=central_sector_id,
        current_sector_id=central_sector_id,
        is_read=False
    )

    db.session.add(conversation)
    db.session.commit()

     # 🔥 inicia o historico da conversa
    log_conversation_event(
        conversation=conversation,
        event_type="created",
        to_sector_id=conversation.current_sector_id
    )
    ensure_conversation_routing(conversation)

    # 🔥 SLA padrão
    sla_minutes = settings.default_sla_minutes if settings else 1

    if conversation.current_sector_id:
        sector = db.session.get(Sector, conversation.current_sector_id)
        if sector and sector.sla_minutes:
            sla_minutes = sector.sla_minutes

    start_sla_for_conversation(conversation, sla_minutes)

    return conversation
