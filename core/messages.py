# core/messages.py
from models import db, Message, Conversation
from datetime import datetime
from extensions import socketio



def create_message(
    conversation_id,
    sender=None,
    content="",
    type="text",
    media_url=None,
    sender_type=None,
    message_type=None,
    sender_user_id=None,
    external_message_id=None,
    created_at=None,
):
    resolved_sender_type = sender_type or sender
    resolved_message_type = message_type or type

    conversation = db.session.get(Conversation, conversation_id)
    resolved_created_at = created_at or datetime.utcnow()

    if external_message_id:
        existing = Message.query.filter_by(
            conversation_id=conversation_id,
            external_message_id=external_message_id,
        ).first()
        if existing:
            return existing

    msg = Message(
        conversation_id=conversation_id,
        company_id=conversation.company_id if conversation else None,
        sender_user_id=sender_user_id,
        sender=resolved_sender_type,
        sender_type=resolved_sender_type,
        content=content,
        type=resolved_message_type,
        message_type=resolved_message_type,
        media_url=media_url,
        external_message_id=external_message_id,
        created_at=resolved_created_at
    )

    if conversation:
        conversation.is_read = resolved_sender_type != "agent"
        if not conversation.updated_at or resolved_created_at >= conversation.updated_at:
            conversation.updated_at = resolved_created_at
        if not conversation.last_message_at or resolved_created_at >= conversation.last_message_at:
            conversation.last_message_at = resolved_created_at
        if conversation.is_read:
            socketio.emit(
                "conversation_unread",
                {"conversation_id": conversation.id},
            )

    db.session.add(msg)

    # Mantido para a transição do modelo novo, mesmo sem coluna persistida ainda.

    # 🔴 Se mensagem NÃO for do agente → marca conversa como NÃO LIDA
    db.session.commit()
    return msg
