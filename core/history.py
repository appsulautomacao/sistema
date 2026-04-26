from datetime import datetime
from db import db
from core.routing import get_conversation_routings
from core.datetime_utils import serialize_utc
from models import ConversationHistory, Sector, User


def log_conversation_event(
    conversation,
    action_type=None,
    event_type=None,
    user_id=None,
    sector_id=None,
    from_sector_id=None,
    to_sector_id=None,
    metadata=None
):
    resolved_event_type = event_type or action_type
    resolved_sector_id = to_sector_id if to_sector_id is not None else sector_id

    event = ConversationHistory(
        conversation_id=conversation.id,
        company_id=conversation.company_id,
        user_id=user_id,
        sector_id=resolved_sector_id,
        action_type=resolved_event_type,
        event_type=resolved_event_type,
        from_sector_id=from_sector_id,
        to_sector_id=to_sector_id if to_sector_id is not None else resolved_sector_id,
        metadata_json=metadata,
        created_at=datetime.utcnow()
    )

    db.session.add(event)
    db.session.commit()
    return event


def serialize_history_event(event):
    resolved_event_type = event.event_type or event.action_type
    user = db.session.get(User, event.user_id) if event.user_id else None
    from_sector = db.session.get(Sector, event.from_sector_id) if event.from_sector_id else None
    to_sector = db.session.get(Sector, event.to_sector_id) if event.to_sector_id else None
    sector = db.session.get(Sector, event.sector_id) if event.sector_id else None

    return {
        "id": event.id,
        "event_type": resolved_event_type,
        "action_type": resolved_event_type,
        "user_id": event.user_id,
        "user_name": user.name if user else None,
        "sector_id": event.sector_id,
        "sector_name": sector.name if sector else None,
        "from_sector_id": event.from_sector_id,
        "from_sector_name": from_sector.name if from_sector else None,
        "to_sector_id": event.to_sector_id,
        "to_sector_name": to_sector.name if to_sector else None,
        "metadata": event.metadata_json or {},
        "created_at": serialize_utc(event.created_at),
    }


def get_conversation_history_events(conversation_id):
    history = ConversationHistory.query.filter_by(
        conversation_id=conversation_id
    ).order_by(ConversationHistory.created_at.asc()).all()
    return [serialize_history_event(event) for event in history]


def build_routing_audit(conversation):
    events = get_conversation_history_events(conversation.id)
    routing_events = [
        event for event in events
        if event["event_type"] in ["created", "assigned", "sector_changed", "sent_message"]
    ]

    sector_path = []
    for event in routing_events:
        sector_name = event["to_sector_name"] or event["sector_name"]
        if sector_name and (not sector_path or sector_path[-1] != sector_name):
            sector_path.append(sector_name)

    return {
        "conversation_id": conversation.id,
        "client_name": conversation.client_name,
        "client_phone": conversation.client_phone,
        "status": conversation.status,
        "current_sector": conversation.current_sector.name if conversation.current_sector else None,
        "assigned_to": conversation.agent.name if conversation.agent else None,
        "created_at": serialize_utc(conversation.created_at),
        "last_message_at": serialize_utc(conversation.last_message_at),
        "sector_path": sector_path,
        "events": routing_events,
        "routings": get_conversation_routings(conversation.id),
    }
