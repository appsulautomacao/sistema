import base64
import os

from flask import Blueprint, jsonify, request, abort
from flask_login import login_required, current_user
from models import (
    Conversation,
    Message,
    SLAEvent,
    User,
    Sector,
    ConversationHistory
)
from core.permissions import (
    is_admin,
    is_central_user,
    can_access_sector,
    can_open_conversation,
    can_move_conversation,
    can_assign_conversation
)
from core.assistant_ai import generate_company_assistant_reply
from core.history import get_conversation_history_events, log_conversation_event
from core.messages import create_message
from core.routing import assign_routing_user, close_conversation_routing, ensure_conversation_routing, get_conversation_routings
from core.sla import resolve_sla
from core.metrics import get_first_response_time
from core.attachments import ensure_message_attachment
from core.attachment_storage import register_existing_upload
from adapters.whatsapp.service import (
    build_remote_jid_candidates,
    find_messages_by_remote_jid,
    find_latest_chat_message,
    get_company_whatsapp_instance,
    send_media_message,
    send_text_message,
    send_whatsapp_audio,
    sync_conversation_messages,
)
from db import db
from extensions import socketio
from core.datetime_utils import serialize_utc


api_conv_bp = Blueprint("api_conversations", __name__, url_prefix="/api")


def _read_upload_as_base64(relative_media_path):
    uploads_root = os.path.join(os.getcwd(), "uploads")
    full_path = os.path.join(uploads_root, relative_media_path.replace("/", os.sep))
    if not os.path.isfile(full_path):
        raise FileNotFoundError(full_path)

    with open(full_path, "rb") as handle:
        return base64.b64encode(handle.read()).decode("ascii")


def _serialize_message_row(message):
    if not message:
        return None

    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "sender_type": message.sender_type or message.sender,
        "content": message.content,
        "external_message_id": message.external_message_id,
        "created_at": serialize_utc(message.created_at),
    }


def _latest_provider_snapshot(instance, conversation):
    if not instance or not conversation:
        return {
            "instance_name": None,
            "lookup_candidates": [],
            "records_found": 0,
            "latest_record": None,
            "latest_client_record": None,
            "lookup_errors": [],
        }

    records = []
    seen_ids = set()
    lookup_errors = []
    lookup_candidates = build_remote_jid_candidates(conversation.client_phone)

    for remote_jid in lookup_candidates:
        try:
            current_records = find_messages_by_remote_jid(instance, remote_jid)
        except Exception as exc:
            lookup_errors.append({"remote_jid": remote_jid, "error": str(exc)})
            continue

        for record in current_records:
            key_data = record.get("key", {}) or {}
            record_id = key_data.get("id") or f"{key_data.get('remoteJid')}:{record.get('messageTimestamp')}"
            if record_id in seen_ids:
                continue
            seen_ids.add(record_id)
            records.append(record)

    def serialize_record(record):
        if not record:
            return None

        key_data = record.get("key", {}) or {}
        message_data = record.get("message", {}) or {}

        content = (
            message_data.get("conversation")
            or message_data.get("extendedTextMessage", {}).get("text")
            or message_data.get("imageMessage", {}).get("caption")
            or message_data.get("documentMessage", {}).get("fileName")
            or ""
        )

        timestamp = record.get("messageTimestamp")
        created_at = None
        if timestamp:
            from datetime import datetime
            created_at = serialize_utc(datetime.utcfromtimestamp(timestamp))

        return {
            "external_message_id": key_data.get("id"),
            "remote_jid": key_data.get("remoteJid"),
            "sender_pn": key_data.get("senderPn"),
            "from_me": bool(key_data.get("fromMe")),
            "content": content,
            "created_at": created_at,
            "message_timestamp": timestamp,
        }

    latest_record = None
    latest_client_record = None
    if records:
        records.sort(key=lambda item: item.get("messageTimestamp") or 0, reverse=True)
        latest_record = records[0]
        latest_client_record = next(
            (
                item for item in records
                if not (item.get("key", {}) or {}).get("fromMe")
            ),
            None
        )
    latest_chat_record = find_latest_chat_message(instance, conversation)

    return {
        "instance_name": instance.instance_name,
        "lookup_candidates": lookup_candidates,
        "records_found": len(records),
        "latest_record": serialize_record(latest_record),
        "latest_client_record": serialize_record(latest_client_record),
        "latest_chat_record": serialize_record(latest_chat_record),
        "lookup_errors": lookup_errors,
    }


# =====================================================
# DASHBOARD CONVERSATIONS
# =====================================================
@api_conv_bp.route("/dashboard/conversations")
@login_required
def dashboard_conversations():
    instance = get_company_whatsapp_instance(current_user.company_id)

    is_central = is_central_user()

    if is_admin():
        conversations = Conversation.query.filter_by(
            company_id=current_user.company_id
        ).all()

    elif is_central:
        # 🔥 CENTRAL vê apenas não classificadas
        conversations = Conversation.query.filter(
            Conversation.company_id == current_user.company_id,
            Conversation.current_sector_id == current_user.sector_id
        ).all()

    else:
        conversations = Conversation.query.filter_by(
            company_id=current_user.company_id,
            current_sector_id=current_user.sector_id
        ).all()

    data = []

    for c in conversations:
        sync_conversation_messages(instance, c)

        last_message = Message.query.filter_by(
            conversation_id=c.id
        ).order_by(Message.created_at.desc()).first()

        last_event = SLAEvent.query.filter_by(
            conversation_id=c.id
        ).order_by(SLAEvent.created_at.desc()).first()

        last_message_time = last_message.created_at if last_message else c.created_at

        unread_count = Message.query.filter_by(
            conversation_id=c.id,
            sender_type="client"
        ).count() if not c.is_read else 0

        data.append({
            "id": c.id,
            "client_name": c.client_name,
            "client_phone": c.client_phone,
            "status": c.status,
            "is_read": c.is_read,
            "sector": c.current_sector.name if c.current_sector else None,
            "assigned_to": c.assigned_to,
            "user_name": User.query.get(c.assigned_to).name if c.assigned_to else None,
            "is_mine": c.assigned_to == current_user.id,
            "can_assign": can_assign_conversation(c),
            "created_at": serialize_utc(c.created_at),
            "sla_breached": last_event and last_event.event_type == "breached",
            "last_message": last_message.content if last_message else "",
            "last_message_type": (last_message.message_type or last_message.type) if last_message else "text",
            "last_message_time": serialize_utc(last_message_time),
            "unread_count": unread_count
        })

    data.sort(key=lambda x: x["last_message_time"], reverse=True)

    return jsonify(data)


@api_conv_bp.route("/conversations/<int:id>/diagnostics")
@login_required
def conversation_diagnostics(id):
    conversation = Conversation.query.filter_by(
        id=id,
        company_id=current_user.company_id
    ).first_or_404()

    if not can_access_sector(conversation) and not is_admin():
        return jsonify({"error": "Sem permissao"}), 403

    latest_message = Message.query.filter_by(
        conversation_id=conversation.id
    ).order_by(Message.created_at.desc()).first()

    latest_client_message = Message.query.filter_by(
        conversation_id=conversation.id,
        sender_type="client",
    ).order_by(Message.created_at.desc()).first()

    latest_agent_message = Message.query.filter_by(
        conversation_id=conversation.id,
        sender_type="agent",
    ).order_by(Message.created_at.desc()).first()

    latest_history_event = ConversationHistory.query.filter_by(
        conversation_id=conversation.id
    ).order_by(ConversationHistory.created_at.desc()).first()

    instance = get_company_whatsapp_instance(current_user.company_id)
    provider_snapshot = _latest_provider_snapshot(instance, conversation)

    latest_provider_client = provider_snapshot.get("latest_client_record") or {}
    lag_detected = bool(
        latest_provider_client.get("external_message_id")
        and latest_provider_client.get("external_message_id") != (
            latest_client_message.external_message_id if latest_client_message else None
        )
    )

    return jsonify({
        "conversation": {
            "id": conversation.id,
            "client_name": conversation.client_name,
            "client_phone": conversation.client_phone,
            "status": conversation.status,
            "current_sector": conversation.current_sector.name if conversation.current_sector else None,
            "assigned_to": conversation.assigned_to,
            "assigned_user": conversation.agent.name if conversation.agent else None,
            "updated_at": serialize_utc(conversation.updated_at),
            "last_message_at": serialize_utc(conversation.last_message_at),
            "is_read": conversation.is_read,
        },
        "database": {
            "latest_message": _serialize_message_row(latest_message),
            "latest_client_message": _serialize_message_row(latest_client_message),
            "latest_agent_message": _serialize_message_row(latest_agent_message),
        },
        "history": {
            "latest_event_type": latest_history_event.event_type or latest_history_event.action_type if latest_history_event else None,
            "latest_event_at": serialize_utc(latest_history_event.created_at) if latest_history_event else None,
        },
        "provider": provider_snapshot,
        "diagnosis": {
            "lag_detected": lag_detected,
            "db_latest_client_external_id": latest_client_message.external_message_id if latest_client_message else None,
            "provider_latest_client_external_id": latest_provider_client.get("external_message_id"),
        }
    })


# =====================================================
# GET CONVERSATION
# =====================================================
@api_conv_bp.route("/conversations/<int:id>")
@login_required
def get_conversation(id):

    conversation = Conversation.query.filter_by(
        id=id,
        company_id=current_user.company_id
    ).first_or_404()

    allowed, reason = can_open_conversation(conversation)

    if not allowed:
        if reason == "Já assumida":
            assigned_user = User.query.get(conversation.assigned_to)
            return jsonify({
                "error": "Já assumida",
                "assigned_to": assigned_user.name
            }), 403

    instance = get_company_whatsapp_instance(current_user.company_id)
    sync_conversation_messages(instance, conversation)

    messages = Message.query.filter_by(
        conversation_id=conversation.id
    ).order_by(Message.created_at.asc()).all()

    return jsonify({
        "id": conversation.id,
        "client_name": conversation.client_name,
        "messages": [m.to_dict() for m in messages]
    })


@api_conv_bp.route("/conversations/<int:id>/assistant-suggestion")
@login_required
def get_assistant_suggestion(id):

    conversation = Conversation.query.filter_by(
        id=id,
        company_id=current_user.company_id
    ).first_or_404()

    allowed, reason = can_open_conversation(conversation)
    if not allowed and not is_admin():
        payload = {"error": reason or "Sem permissao"}
        if reason == "Já assumida":
            assigned_user = User.query.get(conversation.assigned_to)
            payload["assigned_to"] = assigned_user.name if assigned_user else None
        return jsonify(payload), 403

    messages = Message.query.filter_by(
        conversation_id=conversation.id
    ).order_by(Message.created_at.asc()).all()

    latest_client_message = next(
        (message for message in reversed(messages) if (message.sender_type or message.sender) == "client" and (message.content or "").strip()),
        None
    )

    if not latest_client_message:
        return jsonify({
            "reply": "",
            "provider": "fallback",
            "model": "",
            "reason": "no_client_message",
            "rag_result": {"configured_path": None, "results": []},
        })

    result = generate_company_assistant_reply(
        company_id=current_user.company_id,
        customer_message=latest_client_message.content or "",
        conversation_messages=[message.to_dict() for message in messages],
    )

    return jsonify(result)


# =====================================================
# ASSIGN CONVERSATION
# =====================================================
@api_conv_bp.route("/conversations/<int:conversation_id>/assign", methods=["POST"])
@login_required
def assign_conversation(conversation_id):

    print("ASSIGN CHAMADO", conversation_id)

    conversation = Conversation.query.filter_by(
        id=conversation_id,
        company_id=current_user.company_id
    ).first_or_404()

    print("CONVERSA:", conversation.id)

    if not can_assign_conversation(conversation):
        print("SEM PERMISSAO")
        return jsonify({"error": "Sem permissão"}), 403

    print("PODE ASSUMIR")

    conversation.assigned_to = current_user.id
    db.session.commit()

    log_conversation_event(
        conversation=conversation,
        event_type="assigned",
        user_id=current_user.id,
        sector_id=conversation.current_sector_id
    )
    assign_routing_user(conversation)

    print("ASSUMIDA")

    return jsonify({"status": "ok"})

# =====================================================
# SEND MESSAGE
# =====================================================
@api_conv_bp.route("/messages", methods=["POST"])
@login_required
def send_message():

    data = request.json
    conversation_id = data["conversation_id"]

    conversation = Conversation.query.filter_by(
        id=conversation_id,
        company_id=current_user.company_id
    ).first_or_404()

    if (not is_admin() and conversation.assigned_to != current_user.id):
        return jsonify({"error": "Você precisa assumir esta conversa"}), 403

    # 🔥 AGORA FORA DO IF
    original_content = data.get("content") or ""
    original_filename = data.get("original_filename") or ""
    mime_type = data.get("mime_type") or ""
    message_type = data.get("message_type") or data.get("type", "text")

    if message_type == "text":

        sector = db.session.get(Sector, conversation.current_sector_id)
        sector_name = sector.name if sector else "Central"

        prefix = f"{sector_name} - {current_user.name}:\n"
        formatted_content = prefix + original_content

    else:
        formatted_content = original_content or original_filename

    instance = get_company_whatsapp_instance(current_user.company_id)
    if not instance:
        return jsonify({"error": "WhatsApp da empresa nao esta configurado"}), 400

    external_response = None
    external_message_id = None
    if message_type == "text":
        try:
            external_response = send_text_message(
                instance,
                conversation.client_phone,
                formatted_content,
            )
            resolved_remote_jid = external_response.get("key", {}).get("remoteJid")
            if resolved_remote_jid and conversation.client_phone != resolved_remote_jid:
                conversation.client_phone = resolved_remote_jid
                db.session.commit()
            external_message_id = (
                external_response.get("key", {}).get("id")
                or external_response.get("id")
            )
        except Exception as exc:
            return jsonify({"error": f"Falha ao enviar no WhatsApp: {exc}"}), 502
    elif data.get("media_url"):
        try:
            media_base64 = _read_upload_as_base64(data.get("media_url"))
            original_filename = original_filename or os.path.basename(data.get("media_url"))
            mime_type = mime_type or "application/octet-stream"
            caption = original_content or ""

            if message_type == "audio":
                external_response = send_whatsapp_audio(
                    instance,
                    conversation.client_phone,
                    media_base64,
                )
            else:
                outbound_media_type = message_type if message_type in {"image", "video"} else "document"
                external_response = send_media_message(
                    instance,
                    conversation.client_phone,
                    outbound_media_type,
                    mime_type,
                    media_base64,
                    original_filename,
                    caption=caption,
                )

            resolved_remote_jid = external_response.get("key", {}).get("remoteJid")
            if resolved_remote_jid and conversation.client_phone != resolved_remote_jid:
                conversation.client_phone = resolved_remote_jid
                db.session.commit()
            external_message_id = (
                external_response.get("key", {}).get("id")
                or external_response.get("id")
            )
        except Exception as exc:
            return jsonify({"error": f"Falha ao enviar midia no WhatsApp: {exc}"}), 502

    msg = create_message(
        conversation_id=conversation_id,
        sender_type="agent",
        sender_user_id=current_user.id,
        content=formatted_content,
        message_type=message_type,
        media_url=data.get("media_url"),
        external_message_id=external_message_id,
    )

    if message_type != "text" and data.get("media_url"):
        try:
            stored_media = register_existing_upload(
                current_user.company_id,
                data.get("media_url"),
            )
            ensure_message_attachment(
                message=msg,
                attachment_type=message_type,
                original_filename=original_filename or stored_media.get("original_filename") or original_content,
                storage_key=stored_media.get("storage_key"),
                safe_filename=stored_media.get("safe_filename"),
                mime_type=stored_media.get("mime_type"),
                extension=stored_media.get("extension"),
                size_bytes=stored_media.get("size_bytes"),
                full_path=stored_media.get("full_path"),
                is_inbound=False,
                download_status="ready",
            )
        except Exception as exc:
            print(f"Falha ao registrar anexo enviado: {exc}")

    log_conversation_event(
        conversation=conversation,
        event_type="sent_message",
        user_id=current_user.id,
        sector_id=conversation.current_sector_id
    )

    resolve_event = resolve_sla(conversation)

    if resolve_event:
        socketio.emit(
            "sla_resolved",
            {
                "conversation_id": conversation.id,
                "resolved_at": serialize_utc(resolve_event.actual_response_at)
            }
        )

    socketio.emit(
        "new_message",
        {
            "id": msg.id,
            "conversation_id": msg.conversation_id,
            "sender": msg.sender_type,
            "content": msg.content,
            "type": msg.message_type,
            "media_url": msg.media_url,
            "attachments": [attachment.to_dict() for attachment in msg.attachments],
            "created_at": serialize_utc(msg.created_at)
        },
        room=f"conversation_{msg.conversation_id}"
    )

    return jsonify({
        "id": msg.id,
        "conversation_id": msg.conversation_id,
        "sender": msg.sender_type,
        "content": msg.content,
        "attachments": [attachment.to_dict() for attachment in msg.attachments],
        "created_at": serialize_utc(msg.created_at)
    })

# =====================================================
# MARK READ
# =====================================================
@api_conv_bp.route("/conversations/<int:conversation_id>/read", methods=["POST"])
@login_required
def mark_conversation_read(conversation_id):

    conversation = Conversation.query.filter_by(
        id=conversation_id,
        company_id=current_user.company_id
    ).first_or_404()

    if not can_access_sector(conversation):
        return jsonify({"error": "Sem permissão"}), 403

    conversation.is_read = True
    db.session.commit()

    socketio.emit(
        "conversation_read",
        {"conversation_id": conversation.id}
    )

    return {"status": "ok"}


# =====================================================
# MARK UNREAD
# =====================================================
@api_conv_bp.route("/conversations/<int:conversation_id>/unread", methods=["POST"])
@login_required
def mark_conversation_unread(conversation_id):

    conversation = Conversation.query.filter_by(
        id=conversation_id,
        company_id=current_user.company_id
    ).first_or_404()

    if not can_access_sector(conversation):
        return jsonify({"error": "Sem permissão"}), 403

    conversation.is_read = False
    db.session.commit()

    socketio.emit(
        "conversation_unread",
        {"conversation_id": conversation.id}
    )

    return {"status": "ok"}


# =====================================================
# CHANGE SECTOR
# =====================================================
@api_conv_bp.route("/conversations/<int:conversation_id>/sector", methods=["POST"])
@login_required
def change_sector(conversation_id):

    conversation = Conversation.query.filter_by(
        id=conversation_id,
        company_id=current_user.company_id
    ).first_or_404()

    novo_setor_id = request.json.get("sector_id")

    if not novo_setor_id:
        return jsonify({"error": "Setor inválido"}), 400

    # 🔥 CENTRAL pode mover sempre
    is_central = is_central_user()

    if not is_central and not can_move_conversation(conversation):
        return jsonify({"error": "Você não pode mover esta conversa"}), 403

    # Atualiza setor
    setor_anterior_id = conversation.current_sector_id
    close_conversation_routing(conversation.id)
    conversation.current_sector_id = novo_setor_id
    conversation.sector_id = novo_setor_id
    conversation.assigned_to = None
    conversation.is_read = False

    db.session.commit()
    ensure_conversation_routing(conversation, transferred_by=current_user.id)

    log_conversation_event(
        conversation=conversation,
        event_type="sector_changed",
        user_id=current_user.id,
        from_sector_id=setor_anterior_id,
        to_sector_id=novo_setor_id
    )

    # Realtime
    socketio.emit("conversation_moved", {
        "conversation_id": conversation.id,
        "sector_id": novo_setor_id
    })

    return jsonify({"status": "ok"})


# =====================================================
# CONVERSATION HISTORY
# =====================================================
@api_conv_bp.route("/conversations/<int:conversation_id>/history")
@login_required
def get_conversation_history(conversation_id):

    conversation = Conversation.query.filter_by(
        id=conversation_id,
        company_id=current_user.company_id
    ).first_or_404()

    return jsonify(get_conversation_history_events(conversation.id))


@api_conv_bp.route("/conversations/<int:conversation_id>/metrics")
@login_required
def get_conversation_metrics(conversation_id):

    conversation = Conversation.query.filter_by(
        id=conversation_id,
        company_id=current_user.company_id
    ).first_or_404()

    if not can_access_sector(conversation) and not is_admin() and not is_central_user():
        return jsonify({"error": "Sem permissao"}), 403

    first_response = get_first_response_time(conversation.id)

    return jsonify({
        "first_response_seconds": first_response
    })


@api_conv_bp.route("/conversations/<int:conversation_id>/routing")
@login_required
def get_conversation_routing(conversation_id):
    conversation = Conversation.query.filter_by(
        id=conversation_id,
        company_id=current_user.company_id
    ).first_or_404()

    if not can_access_sector(conversation) and not is_admin() and not is_central_user():
        return jsonify({"error": "Sem permissao"}), 403

    return jsonify(get_conversation_routings(conversation.id))
