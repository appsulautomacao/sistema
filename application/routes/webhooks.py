import os

from flask import Blueprint, request, jsonify
from extensions import socketio
from adapters.whatsapp.service import extract_instance_name, get_instance_by_name
from core.billing_service import enqueue_pagseguro_payload
from core.datetime_utils import serialize_utc

webhooks_bp = Blueprint("webhooks", __name__)


@webhooks_bp.route("/webhooks/evolution", methods=["POST"])
def evolution_webhook():
    from adapters.whatsapp.evolution import handle_evolution_webhook

    payload = request.json
    instance_name = extract_instance_name(payload or {})
    instance = get_instance_by_name(instance_name)
    if not instance:
        return jsonify({"error": "instance_not_found"}), 400

    provided_secret = request.headers.get("X-Webhook-Secret") or request.headers.get("x-webhook-secret")
    if provided_secret and instance.webhook_secret and provided_secret != instance.webhook_secret:
        return jsonify({"error": "invalid_webhook_secret"}), 403

    conversation, message = handle_evolution_webhook(payload)

    if not conversation or not message:
        return jsonify({"status": "ignored"})

    socketio.emit(
        "new_message",
        {
            "id": message.id,
            "conversation_id": conversation.id,
            "sender": message.sender_type or message.sender,
            "content": message.content,
            "type": message.message_type or message.type,
            "media_url": message.media_url,
            "attachments": [attachment.to_dict() for attachment in message.attachments],
            "created_at": serialize_utc(message.created_at)
        },
        room=f"conversation_{conversation.id}"
    )
    socketio.emit(
        "new_message",
        {
            "id": message.id,
            "conversation_id": conversation.id,
            "sender": message.sender_type or message.sender,
            "content": message.content,
            "type": message.message_type or message.type,
            "media_url": message.media_url,
            "attachments": [attachment.to_dict() for attachment in message.attachments],
            "created_at": serialize_utc(message.created_at)
        },
        room=f"company_{conversation.company_id}"
    )

    return jsonify({"status": "ok"})


@webhooks_bp.route("/webhooks/pagseguro", methods=["POST"])
def pagseguro_webhook():
    configured_secret = (os.getenv("PAGSEGURO_WEBHOOK_SECRET") or "").strip()
    provided_secret = (
        request.headers.get("X-PagSeguro-Webhook-Secret")
        or request.headers.get("x-pagseguro-webhook-secret")
        or ""
    ).strip()

    if configured_secret and provided_secret != configured_secret:
        return jsonify({"error": "invalid_webhook_secret"}), 403

    payload = request.get_json(silent=True) or {}
    response, status_code = enqueue_pagseguro_payload(payload=payload)
    return jsonify(response), status_code
