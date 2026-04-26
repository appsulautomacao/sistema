from db import db
from models import AILog, Conversation, Sector

from core.ai_service import classify_text_to_company_sector
from core.conversation_cycles import has_agent_message_in_current_cycle
from core.history import log_conversation_event
from core.routing import close_conversation_routing, ensure_conversation_routing


def _get_sector_by_name(company_id, sector_name):
    return Sector.query.filter_by(
        company_id=company_id,
        name=sector_name,
    ).first()


def should_classify_conversation(conversation: Conversation):
    if not conversation:
        return False

    current_sector = db.session.get(Sector, conversation.current_sector_id) if conversation.current_sector_id else None
    if current_sector and not current_sector.is_central:
        return False

    # Depois que a conversa entrou em atendimento humano, a IA nao deve mais
    # retira-la da central automaticamente a cada nova mensagem do cliente.
    if conversation.assigned_to:
        return False

    if has_agent_message_in_current_cycle(conversation.id):
        return False

    return True


def classify_conversation_sector(conversation: Conversation, text: str):
    """
    Classifica automaticamente uma conversa que ainda esta na central.
    Se a conversa ja estiver em um setor operacional, nao reclassifica.
    """

    if not should_classify_conversation(conversation):
        return conversation

    result = classify_text_to_company_sector(conversation.company_id, text)
    sector = _get_sector_by_name(conversation.company_id, result.sector_name)

    if not sector:
        return {
            "conversation": conversation,
            "changed_sector": False,
            "sector": None,
            "result": result,
        }

    previous_sector_id = conversation.current_sector_id
    changed_sector = previous_sector_id != sector.id

    if changed_sector:
        close_conversation_routing(conversation.id)
        conversation.current_sector_id = sector.id
        conversation.sector_id = sector.id
        conversation.assigned_to = None
        conversation.is_read = False
        db.session.commit()
        ensure_conversation_routing(
            conversation,
            transfer_reason="ai_auto_classification",
        )
        log_conversation_event(
            conversation=conversation,
            event_type="sector_changed",
            from_sector_id=previous_sector_id,
            to_sector_id=sector.id,
            metadata={
                "source": "ai",
                "provider": result.provider,
                "model_name": result.model_name,
            },
        )

    ai_log = AILog(
        conversation_id=conversation.id,
        company_id=conversation.company_id,
        input_text=text,
        predicted_sector=sector.name,
        provider=result.provider,
        model_name=result.model_name,
        used_fallback=result.used_fallback,
        raw_output=result.raw_output,
        failure_reason=result.reason,
    )
    db.session.add(ai_log)
    db.session.commit()

    return {
        "conversation": conversation,
        "changed_sector": changed_sector,
        "sector": sector,
        "result": result,
    }
