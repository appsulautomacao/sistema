from datetime import datetime

from db import db
from core.datetime_utils import serialize_utc
from models import ConversationRouting, Sector, User


def get_open_routing(conversation_id):
    return ConversationRouting.query.filter_by(
        conversation_id=conversation_id,
        left_at=None,
    ).order_by(ConversationRouting.entered_at.desc()).first()


def ensure_conversation_routing(conversation, transferred_by=None, transfer_reason=None):
    if not conversation.current_sector_id:
        return None

    routing = get_open_routing(conversation.id)
    if routing and routing.sector_id == conversation.current_sector_id:
        if conversation.assigned_to and routing.assigned_to != conversation.assigned_to:
            routing.assigned_to = conversation.assigned_to
            db.session.commit()
        return routing

    if routing and routing.left_at is None:
        routing.left_at = datetime.utcnow()

    routing = ConversationRouting(
        conversation_id=conversation.id,
        company_id=conversation.company_id,
        sector_id=conversation.current_sector_id,
        assigned_to=conversation.assigned_to,
        transferred_by=transferred_by,
        transfer_reason=transfer_reason,
        entered_at=datetime.utcnow(),
    )
    db.session.add(routing)
    db.session.commit()
    return routing


def close_conversation_routing(conversation_id):
    routing = get_open_routing(conversation_id)
    if not routing:
        return None

    routing.left_at = datetime.utcnow()
    db.session.commit()
    return routing


def assign_routing_user(conversation):
    routing = get_open_routing(conversation.id)
    if not routing:
        return ensure_conversation_routing(conversation)

    routing.assigned_to = conversation.assigned_to
    db.session.commit()
    return routing


def serialize_routing(routing):
    duration_seconds = None
    if routing.left_at:
        duration_seconds = int((routing.left_at - routing.entered_at).total_seconds())

    sector = db.session.get(Sector, routing.sector_id) if routing.sector_id else None
    assigned_user = db.session.get(User, routing.assigned_to) if routing.assigned_to else None
    transferred_by_user = db.session.get(User, routing.transferred_by) if routing.transferred_by else None

    return {
        "id": routing.id,
        "conversation_id": routing.conversation_id,
        "sector_id": routing.sector_id,
        "sector_name": sector.name if sector else None,
        "assigned_to": routing.assigned_to,
        "assigned_to_name": assigned_user.name if assigned_user else None,
        "transferred_by": routing.transferred_by,
        "transferred_by_name": transferred_by_user.name if transferred_by_user else None,
        "transfer_reason": routing.transfer_reason,
        "entered_at": serialize_utc(routing.entered_at),
        "left_at": serialize_utc(routing.left_at),
        "duration_seconds": duration_seconds,
        "is_open": routing.left_at is None,
    }


def get_conversation_routings(conversation_id):
    routings = ConversationRouting.query.filter_by(
        conversation_id=conversation_id
    ).order_by(ConversationRouting.entered_at.asc()).all()
    return [serialize_routing(routing) for routing in routings]
