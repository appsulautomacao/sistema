# core/sla.py

from datetime import datetime, timedelta
from models import db, SLAEvent, Notification, Sector, Conversation


def start_sla_for_conversation(conversation: Conversation, sla_minutes: int):
    expected_time = datetime.utcnow() + timedelta(minutes=sla_minutes)

    sla_event = SLAEvent(
        conversation_id=conversation.id,
        event_type="started",
        expected_response_at=expected_time
    )

    db.session.add(sla_event)
    db.session.commit()

    return sla_event


def check_sla_breach(conversation: Conversation):
    # evento SLA ativo
    active_event = SLAEvent.query.filter_by(
        conversation_id=conversation.id,
        event_type="started"
    ).order_by(SLAEvent.created_at.desc()).first()

    if not active_event:
        return None

    # 🔥 já existe breach para essa conversa?
    already_breached = SLAEvent.query.filter_by(
        conversation_id=conversation.id,
        event_type="breached"
    ).first()

    if already_breached:
        return None

    now = datetime.utcnow()

    if now > active_event.expected_response_at:
        breach_event = SLAEvent(
            conversation_id=conversation.id,
            event_type="breached",
            expected_response_at=active_event.expected_response_at,
            actual_response_at=now
        )

        db.session.add(breach_event)

        notification = Notification(
            conversation_id=conversation.id,
            message=f"SLA estourado para a conversa {conversation.id}",
            type="sla_breach"
        )

        db.session.add(notification)
        db.session.commit()

        return breach_event

    return None


def resolve_sla(conversation: Conversation):
    active_event = SLAEvent.query.filter_by(
        conversation_id=conversation.id,
        event_type="started"
    ).order_by(SLAEvent.created_at.desc()).first()

    if not active_event:
        return None

    now = datetime.utcnow()

    resolve_event = SLAEvent(
        conversation_id=conversation.id,
        event_type="resolved",
        expected_response_at=active_event.expected_response_at,
        actual_response_at=now
    )

    db.session.add(resolve_event)
    db.session.commit()

    return resolve_event



