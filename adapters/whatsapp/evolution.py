from core.ai import classify_conversation_sector
from core.assistant_ai import auto_reply_to_central_conversation
from core.conversations import get_or_create_conversation
from core.history import log_conversation_event
from core.messages import create_message
from datetime import datetime
from adapters.whatsapp.service import (
    canonicalize_client_phone,
    extract_instance_name,
    get_instance_by_name,
    sync_instance_status,
)
from core.attachments import ensure_message_attachment
from models import Conversation, Message


def _coerce_size_bytes(value):
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, dict):
        low = value.get("low", 0) or 0
        high = value.get("high", 0) or 0
        unsigned = bool(value.get("unsigned", True))
        combined = (int(high) << 32) | int(low)
        if not unsigned and high < 0:
            return -combined
        return combined
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_message_data(payload):
    if not isinstance(payload, dict):
        return {}

    data = payload.get("data")
    candidates = []

    if isinstance(data, dict):
        if isinstance(data.get("messages"), list) and data.get("messages"):
            candidates.append(data["messages"][0])
        candidates.append(data)

    if isinstance(payload.get("messages"), list) and payload.get("messages"):
        candidates.append(payload["messages"][0])

    candidates.append(payload)

    for candidate in candidates:
        if isinstance(candidate, dict) and (
            candidate.get("key")
            or candidate.get("message")
            or candidate.get("pushName")
        ):
            return candidate

    return {}


def _unwrap_message_content(message_content):
    current = message_content or {}

    # Alguns eventos da Evolution encapsulam o conteudo real nestes wrappers.
    for wrapper_key in ("ephemeralMessage", "viewOnceMessage", "viewOnceMessageV2"):
        wrapper = current.get(wrapper_key)
        if isinstance(wrapper, dict) and isinstance(wrapper.get("message"), dict):
            current = wrapper.get("message") or {}

    return current


def _extract_content_fields(message_content):
    normalized_content = _unwrap_message_content(message_content)

    if "conversation" in normalized_content:
        return "text", normalized_content.get("conversation", ""), None, {}

    if "extendedTextMessage" in normalized_content:
        text_data = normalized_content.get("extendedTextMessage", {}) or {}
        return "text", text_data.get("text", ""), None, {}

    if "imageMessage" in normalized_content:
        image_data = normalized_content["imageMessage"]
        return (
            "image",
            image_data.get("caption", ""),
            image_data.get("url") or image_data.get("directPath") or image_data.get("downloadUrl"),
            {
                "mime_type": image_data.get("mimetype"),
                "size_bytes": _coerce_size_bytes(image_data.get("fileLength") or image_data.get("fileSize")),
            },
        )

    if "audioMessage" in normalized_content:
        audio_data = normalized_content["audioMessage"]
        return (
            "audio",
            "",
            audio_data.get("url") or audio_data.get("directPath") or audio_data.get("downloadUrl"),
            {
                "mime_type": audio_data.get("mimetype"),
                "size_bytes": _coerce_size_bytes(audio_data.get("fileLength") or audio_data.get("fileSize")),
                "extension": ".ogg" if audio_data.get("ptt") else None,
            },
        )

    if "videoMessage" in normalized_content:
        video_data = normalized_content["videoMessage"]
        return (
            "video",
            video_data.get("caption", ""),
            video_data.get("url") or video_data.get("directPath") or video_data.get("downloadUrl"),
            {
                "mime_type": video_data.get("mimetype"),
                "size_bytes": _coerce_size_bytes(video_data.get("fileLength") or video_data.get("fileSize")),
            },
        )

    if "documentMessage" in normalized_content:
        doc_data = normalized_content["documentMessage"]
        return (
            "document",
            doc_data.get("fileName", ""),
            doc_data.get("url") or doc_data.get("directPath") or doc_data.get("downloadUrl"),
            {
                "original_filename": doc_data.get("fileName"),
                "mime_type": doc_data.get("mimetype"),
                "size_bytes": _coerce_size_bytes(doc_data.get("fileLength") or doc_data.get("fileSize")),
            },
        )

    return "unknown", "", None, {}


def handle_evolution_webhook(payload):
    """
    Normaliza payload da Evolution API e persiste no sistema.
    Eventos sem mensagem valida sao ignorados sem quebrar o webhook.
    """
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    instance_name = extract_instance_name(payload)
    instance = get_instance_by_name(instance_name)
    if not instance:
        raise ValueError(f"Instancia nao encontrada para o webhook: {instance_name}")

    # Eventos de conexao/status nao devem retornar 500.
    if isinstance(data, dict) and not data.get("messages") and not data.get("key") and not payload.get("key"):
        sync_instance_status(instance, data)
        return None, None

    company = instance.company
    message_data = _extract_message_data(payload)

    key_data = message_data.get("key", {}) or {}
    remote_jid = key_data.get("remoteJid")
    sender_pn = key_data.get("senderPn")
    push_name = message_data.get("pushName", "Cliente")

    message_content = message_data.get("message", {}) or {}
    message_type, content, media_url, attachment_meta = _extract_content_fields(message_content)

    if message_type == "unknown":
        if not remote_jid:
            return None, None

    preferred_phone = canonicalize_client_phone(
        remote_jid=remote_jid,
        sender_pn=sender_pn,
    )
    message_timestamp = message_data.get("messageTimestamp") or data.get("messageTimestamp")
    created_at = (
        datetime.utcfromtimestamp(message_timestamp)
        if message_timestamp else None
    )
    candidate_phones = []
    for phone in [preferred_phone, remote_jid, sender_pn]:
        if phone and phone not in candidate_phones:
            candidate_phones.append(phone)

    conversation = Conversation.query.filter(
        Conversation.company_id == company.id,
        Conversation.client_phone.in_(candidate_phones),
    ).order_by(Conversation.id.asc()).first()

    if conversation:
        canonical_phone = canonicalize_client_phone(
            remote_jid=remote_jid,
            sender_pn=sender_pn,
            current_phone=conversation.client_phone,
        )
        if canonical_phone and conversation.client_phone != canonical_phone:
            conversation.client_phone = canonical_phone
            conversation.client_name = push_name or conversation.client_name
            from db import db
            db.session.commit()
    else:
        conversation = get_or_create_conversation(
            client_phone=preferred_phone,
            client_name=push_name,
            company_id=company.id,
        )

    external_message_id = key_data.get("id")
    if external_message_id:
        existing_message = Message.query.filter_by(
            conversation_id=conversation.id,
            external_message_id=external_message_id,
        ).first()
        if existing_message:
            return conversation, existing_message

    message = create_message(
        conversation_id=conversation.id,
        sender_type="client",
        content=content,
        message_type=message_type,
        media_url=media_url,
        external_message_id=external_message_id,
        created_at=created_at,
    )
    if message_type != "text" and (media_url or attachment_meta.get("original_filename")):
        ensure_message_attachment(
            message=message,
            attachment_type=message_type,
            original_filename=attachment_meta.get("original_filename") or content,
            provider="evolution",
            provider_message_id=external_message_id,
            provider_media_url=media_url,
            mime_type=attachment_meta.get("mime_type"),
            extension=attachment_meta.get("extension"),
            size_bytes=attachment_meta.get("size_bytes"),
            is_inbound=True,
            download_status="pending",
        )

    try:
        from models import CompanySettings

        settings = CompanySettings.query.filter_by(
            company_id=conversation.company_id
        ).first()

        if settings and settings.central_ai_enabled:
            classification = classify_conversation_sector(conversation, content)
            routed_sector = classification.get("sector") if isinstance(classification, dict) else None
            if (
                isinstance(classification, dict)
                and classification.get("changed_sector")
                and routed_sector
                and not routed_sector.is_central
            ):
                handoff_message = (
                    f"Entendi. Vou encaminhar seu atendimento para o setor de {routed_sector.name} "
                    "para seguir com voce da melhor forma."
                )
                try:
                    external_response = send_text_message(
                        instance,
                        conversation.client_phone,
                        handoff_message,
                    )
                    external_message_id = (
                        external_response.get("key", {}).get("id")
                        or external_response.get("id")
                    )
                except Exception:
                    external_message_id = None

                handoff_notice = create_message(
                    conversation_id=conversation.id,
                    sender_type="agent",
                    content=handoff_message,
                    message_type="text",
                    external_message_id=external_message_id,
                )
                log_conversation_event(
                    conversation=conversation,
                    event_type="ai_sector_handoff_notice",
                    sector_id=conversation.current_sector_id,
                    metadata={
                        "target_sector": routed_sector.name,
                        "message_id": handoff_notice.id,
                    },
                )
    except Exception as exc:
        print("Erro na IA:", exc)

    try:
        auto_reply_to_central_conversation(instance, conversation, message)
    except Exception as exc:
        print("Erro no pre-atendimento IA:", exc)

    return conversation, message
