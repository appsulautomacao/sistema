from datetime import datetime
import base64
import os
import secrets
import time

import requests

from db import db
from models import Company, Conversation, Message, WhatsAppInstance


EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")
EVOLUTION_BASE_URL = os.getenv("EVOLUTION_BASE_URL", "http://evolution:8080").rstrip("/")
INTERNAL_WEBHOOK_URL = os.getenv(
    "EVOLUTION_INTERNAL_WEBHOOK_URL",
    "http://app:5000/webhooks/evolution",
)


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


def get_company_whatsapp_instance(company_id):
    instance = WhatsAppInstance.query.filter(
        WhatsAppInstance.company_id == company_id,
        WhatsAppInstance.status != "deleted",
    ).order_by(WhatsAppInstance.created_at.desc()).first()
    if instance and not instance.webhook_secret:
        instance.webhook_secret = secrets.token_urlsafe(24)
        db.session.commit()
    return instance


def get_company_by_instance_name(instance_name):
    if not instance_name:
        return None

    instance = WhatsAppInstance.query.filter_by(instance_name=instance_name).first()
    if instance:
        return db.session.get(Company, instance.company_id)
    return None


def get_instance_by_name(instance_name):
    if not instance_name:
        return None

    instance = WhatsAppInstance.query.filter_by(instance_name=instance_name).first()
    if instance and not instance.webhook_secret:
        instance.webhook_secret = secrets.token_urlsafe(24)
        db.session.commit()
    return instance


def extract_instance_name(payload):
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    candidates = [
        payload.get("instanceName") if isinstance(payload, dict) else None,
        payload.get("instance") if isinstance(payload, dict) else None,
        data.get("instanceName") if isinstance(data, dict) else None,
        data.get("instance") if isinstance(data, dict) else None,
        data.get("sender") if isinstance(data, dict) else None,
    ]

    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
        if isinstance(candidate, dict):
            nested = (
                candidate.get("instanceName")
                or candidate.get("name")
                or candidate.get("instance")
            )
            if nested:
                return nested

    return None


def create_company_whatsapp_instance(company_id):
    instance = get_company_whatsapp_instance(company_id)
    if instance:
        return instance, False

    company = db.session.get(Company, company_id)
    instance_name = f"company_{company.id}_{int(time.time())}"

    response = requests.post(
        f"{EVOLUTION_BASE_URL}/instance/create",
        json={
            "instanceName": instance_name,
            "token": "123456",
            "integration": "WHATSAPP-BAILEYS",
            "qrcode": True
        },
        headers={"apikey": EVOLUTION_API_KEY},
    )

    if response.status_code not in [200, 201]:
        raise RuntimeError(response.text)

    instance = WhatsAppInstance(
        company_id=company.id,
        instance_name=instance_name,
        api_key=EVOLUTION_API_KEY,
        webhook_secret=secrets.token_urlsafe(24),
        status="created",
    )
    company.whatsapp_instance = instance_name

    db.session.add(instance)
    db.session.commit()
    ensure_instance_webhook(instance)

    return instance, True


def update_instance_status(instance, status):
    if not instance:
        return

    instance.status = status
    if status == "open":
        instance.last_connection_at = datetime.utcnow()
    instance.company.whatsapp_instance = None if status == "deleted" else instance.instance_name
    db.session.commit()


def sync_instance_status(instance, payload):
    if not instance:
        return None

    if isinstance(payload, str):
        update_instance_status(instance, payload)
        return payload

    if isinstance(payload, dict):
        instance_payload = payload.get("instance")
        state = None
        if isinstance(instance_payload, dict):
            state = instance_payload.get("state")
        elif isinstance(instance_payload, str):
            state = payload.get("state") or instance_payload
        else:
            state = payload.get("state")
        if state:
            update_instance_status(instance, state)
            return state

    return None


def normalize_evolution_status(payload):
    if isinstance(payload, str):
        return payload

    if isinstance(payload, dict):
        instance_payload = payload.get("instance")
        if isinstance(instance_payload, dict):
            return instance_payload.get("state") or payload.get("state") or "unknown"
        if isinstance(instance_payload, str):
            return payload.get("state") or instance_payload or "unknown"
        return payload.get("state") or "unknown"

    return "unknown"


def normalize_whatsapp_target(target):
    if not target:
        return None

    normalized = str(target).strip()
    for suffix in ["@s.whatsapp.net", "@c.us", "@lid"]:
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)]
            break

    return normalized


def canonicalize_client_phone(remote_jid=None, sender_pn=None, current_phone=None):
    candidates = [sender_pn, current_phone, remote_jid]

    for candidate in candidates:
        if not candidate:
            continue

        normalized = str(candidate).strip()
        if normalized.endswith("@s.whatsapp.net") or normalized.endswith("@c.us"):
            return normalized

    for candidate in candidates:
        if candidate:
            return str(candidate).strip()

    return None


def build_remote_jid_candidates(phone):
    if not phone:
        return []

    raw = str(phone).strip()
    normalized = normalize_whatsapp_target(raw)
    candidates = []

    for candidate in [raw, f"{normalized}@s.whatsapp.net", f"{normalized}@c.us", f"{normalized}@lid"]:
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    return candidates


def find_messages_by_remote_jid(instance, remote_jid):
    if not instance or not remote_jid:
        return []

    response = requests.post(
        f"{EVOLUTION_BASE_URL}/chat/findMessages/{instance.instance_name}",
        json={
            "where": {
                "key": {
                    "remoteJid": remote_jid,
                }
            }
        },
        headers={"apikey": EVOLUTION_API_KEY},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json() or {}
    return payload.get("messages", {}).get("records", [])


def find_chats(instance, payload=None):
    if not instance:
        return []

    response = requests.post(
        f"{EVOLUTION_BASE_URL}/chat/findChats/{instance.instance_name}",
        json=payload or {},
        headers={"apikey": EVOLUTION_API_KEY},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json() or []
    return payload if isinstance(payload, list) else []


def resolve_send_target(instance, target):
    if not target:
        return None

    normalized_target = str(target).strip()
    if normalized_target.endswith("@lid"):
        try:
            records = find_messages_by_remote_jid(instance, normalized_target)
            for record in records:
                key_data = record.get("key", {})
                sender_pn = key_data.get("senderPn")
                if sender_pn:
                    return normalize_whatsapp_target(sender_pn)
        except Exception:
            pass

    return normalize_whatsapp_target(normalized_target)


def send_text_message(instance, number, text):
    if not instance:
        raise ValueError("Instancia WhatsApp nao encontrada")

    payload = {
        "number": resolve_send_target(instance, number),
        "text": text,
        "options": {
            "delay": 0,
            "presence": "composing",
        },
    }

    response = requests.post(
        f"{EVOLUTION_BASE_URL}/message/sendText/{instance.instance_name}",
        json=payload,
        headers={"apikey": EVOLUTION_API_KEY},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def send_media_message(instance, number, media_type, mime_type, media_base64_or_url, file_name, caption=""):
    if not instance:
        raise ValueError("Instancia WhatsApp nao encontrada")

    payload = {
        "number": resolve_send_target(instance, number),
        "mediatype": media_type,
        "mimetype": mime_type,
        "caption": caption or "",
        "media": media_base64_or_url,
        "fileName": file_name,
        "delay": 0,
    }

    response = requests.post(
        f"{EVOLUTION_BASE_URL}/message/sendMedia/{instance.instance_name}",
        json=payload,
        headers={"apikey": EVOLUTION_API_KEY},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def send_whatsapp_audio(instance, number, audio_base64_or_url):
    if not instance:
        raise ValueError("Instancia WhatsApp nao encontrada")

    payload = {
        "number": resolve_send_target(instance, number),
        "audio": audio_base64_or_url,
        "delay": 0,
    }

    response = requests.post(
        f"{EVOLUTION_BASE_URL}/message/sendWhatsAppAudio/{instance.instance_name}",
        json=payload,
        headers={"apikey": EVOLUTION_API_KEY},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def get_media_base64(instance, external_message_id, convert_to_mp4=False):
    if not instance:
        raise ValueError("Instancia WhatsApp nao encontrada")
    if not external_message_id:
        raise ValueError("Mensagem externa sem identificador")

    response = requests.post(
        f"{EVOLUTION_BASE_URL}/chat/getBase64FromMediaMessage/{instance.instance_name}",
        json={
            "message": {
                "key": {
                    "id": external_message_id,
                }
            },
            "convertToMp4": convert_to_mp4,
        },
        headers={"apikey": EVOLUTION_API_KEY},
        timeout=30,
    )
    response.raise_for_status()
    return response.json() or {}


def decode_media_base64_payload(payload):
    base64_value = (payload or {}).get("base64")
    if not base64_value:
        raise ValueError("Resposta da Evolution sem base64")

    if "," in base64_value and base64_value.startswith("data:"):
        base64_value = base64_value.split(",", 1)[1]

    return base64.b64decode(base64_value)


def _extract_record_text(record):
    message_data = record.get("message", {}) or {}

    for wrapper_key in ("ephemeralMessage", "viewOnceMessage", "viewOnceMessageV2"):
        wrapper = message_data.get(wrapper_key)
        if isinstance(wrapper, dict) and isinstance(wrapper.get("message"), dict):
            message_data = wrapper.get("message") or {}

    if "conversation" in message_data:
        return "text", message_data.get("conversation", ""), None, {}

    if "extendedTextMessage" in message_data:
        extended_text = message_data.get("extendedTextMessage", {}) or {}
        return "text", extended_text.get("text", ""), None, {}

    if "imageMessage" in message_data:
        image = message_data.get("imageMessage", {})
        return "image", image.get("caption", ""), (
            image.get("url") or image.get("directPath") or image.get("downloadUrl")
        ), {
            "mime_type": image.get("mimetype"),
            "size_bytes": _coerce_size_bytes(image.get("fileLength") or image.get("fileSize")),
        }

    if "audioMessage" in message_data:
        audio = message_data.get("audioMessage", {})
        return "audio", "", (
            audio.get("url") or audio.get("directPath") or audio.get("downloadUrl")
        ), {
            "mime_type": audio.get("mimetype"),
            "size_bytes": _coerce_size_bytes(audio.get("fileLength") or audio.get("fileSize")),
            "extension": ".ogg" if audio.get("ptt") else None,
        }

    if "videoMessage" in message_data:
        video = message_data.get("videoMessage", {})
        return "video", video.get("caption", ""), (
            video.get("url") or video.get("directPath") or video.get("downloadUrl")
        ), {
            "mime_type": video.get("mimetype"),
            "size_bytes": _coerce_size_bytes(video.get("fileLength") or video.get("fileSize")),
        }

    if "documentMessage" in message_data:
        document = message_data.get("documentMessage", {})
        return "document", document.get("fileName", ""), (
            document.get("url") or document.get("directPath") or document.get("downloadUrl")
        ), {
            "original_filename": document.get("fileName"),
            "mime_type": document.get("mimetype"),
            "size_bytes": _coerce_size_bytes(document.get("fileLength") or document.get("fileSize")),
        }

    return "text", "", None, {}


def _normalize_record_remote_jid(record):
    key_data = record.get("key", {}) or {}
    return (
        key_data.get("senderPn")
        or key_data.get("remoteJid")
    )


def _conversation_number_candidates(conversation):
    if not conversation or not conversation.client_phone:
        return set()

    candidates = set()
    for remote_jid in build_remote_jid_candidates(conversation.client_phone):
        normalized = normalize_whatsapp_target(remote_jid)
        if normalized:
            candidates.add(normalized)

    return candidates


def find_latest_chat_message(instance, conversation):
    if not instance or not conversation:
        return None

    candidates = _conversation_number_candidates(conversation)
    if not candidates:
        return None

    try:
        chats = find_chats(instance)
    except Exception:
        return None

    matches = []
    for chat in chats:
        last_message = chat.get("lastMessage") or {}
        key_data = last_message.get("key", {}) or {}
        sender_pn = normalize_whatsapp_target(key_data.get("senderPn"))
        remote_jid = normalize_whatsapp_target(key_data.get("remoteJid"))

        if sender_pn in candidates or remote_jid in candidates:
            matches.append(last_message)

    if not matches:
        return None

    matches.sort(key=lambda item: item.get("messageTimestamp") or 0, reverse=True)
    return matches[0]


def _looks_like_agent_panel_message(content):
    if not content or ":\n" not in content:
        return False

    header = content.split(":\n", 1)[0].strip()
    return " - " in header


def _match_existing_message(conversation_id, sender_type, content, external_message_id, created_at):
    if external_message_id:
        existing = Message.query.filter_by(
            conversation_id=conversation_id,
            external_message_id=external_message_id,
        ).first()
        if existing:
            return existing
        return None

    if not content:
        return None

    candidates = Message.query.filter_by(
        conversation_id=conversation_id,
        sender_type=sender_type,
        content=content,
    ).order_by(Message.created_at.desc()).limit(5).all()

    for candidate in candidates:
        # Sem external_message_id, aceitamos deduplicacao apenas em janela curta
        # para evitar descartar mensagens validas em testes com textos repetidos.
        if abs((candidate.created_at - created_at).total_seconds()) <= 10:
            return candidate

    return None


def sync_conversation_messages(instance, conversation):
    if not instance or not conversation or not conversation.client_phone:
        return []

    records = []
    seen_ids = set()
    for remote_jid in build_remote_jid_candidates(conversation.client_phone):
        try:
            current_records = find_messages_by_remote_jid(instance, remote_jid)
        except Exception:
            continue

        for record in current_records:
            key_data = record.get("key", {}) or {}
            record_id = key_data.get("id") or f"{key_data.get('remoteJid')}:{record.get('messageTimestamp')}"
            if record_id in seen_ids:
                continue
            seen_ids.add(record_id)
            records.append(record)

    imported = []

    from core.attachments import ensure_message_attachment
    from core.messages import create_message

    sorted_records = sorted(
        records,
        key=lambda item: item.get("messageTimestamp") or 0,
    )
    min_timestamp = None
    if conversation.created_at:
        min_timestamp = int(conversation.created_at.timestamp()) - 3600

    for record in sorted_records:
        key_data = record.get("key", {}) or {}
        external_message_id = key_data.get("id")

        message_type, content, media_url, attachment_meta = _extract_record_text(record)
        timestamp = record.get("messageTimestamp")
        if min_timestamp and timestamp and timestamp < min_timestamp:
            continue
        created_at = datetime.utcfromtimestamp(timestamp) if timestamp else datetime.utcnow()

        sender_type = "agent" if key_data.get("fromMe") else "client"
        if sender_type == "agent" and not _looks_like_agent_panel_message(content):
            # Alguns eventos da Evolution chegam com fromMe inconsistente.
            # Se a mensagem nao tem o padrao do painel, tratamos como fala do cliente.
            sender_type = "client"

        existing = _match_existing_message(
            conversation.id,
            sender_type,
            content,
            external_message_id,
            created_at,
        )
        if existing:
            if external_message_id and not existing.external_message_id:
                existing.external_message_id = external_message_id
                db.session.commit()
            continue

        if sender_type != "client":
            continue

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
        db.session.commit()
        imported.append(message)

    latest_chat_message = find_latest_chat_message(instance, conversation)
    if latest_chat_message:
        key_data = latest_chat_message.get("key", {}) or {}
        message_type, content, media_url, attachment_meta = _extract_record_text(latest_chat_message)
        timestamp = latest_chat_message.get("messageTimestamp")
        created_at = datetime.utcfromtimestamp(timestamp) if timestamp else datetime.utcnow()
        sender_type = "agent" if key_data.get("fromMe") else "client"
        if sender_type == "agent" and not _looks_like_agent_panel_message(content):
            sender_type = "client"

        existing = _match_existing_message(
            conversation.id,
            sender_type,
            content,
            key_data.get("id"),
            created_at,
        )

        if not existing and sender_type == "client":
            message = create_message(
                conversation_id=conversation.id,
                sender_type="client",
                content=content,
                message_type=message_type,
                media_url=media_url,
                external_message_id=key_data.get("id"),
                created_at=created_at,
            )
            if message_type != "text" and (media_url or attachment_meta.get("original_filename")):
                ensure_message_attachment(
                    message=message,
                    attachment_type=message_type,
                    original_filename=attachment_meta.get("original_filename") or content,
                    provider="evolution",
                    provider_message_id=key_data.get("id"),
                    provider_media_url=media_url,
                    mime_type=attachment_meta.get("mime_type"),
                    extension=attachment_meta.get("extension"),
                    size_bytes=attachment_meta.get("size_bytes"),
                    is_inbound=True,
                    download_status="pending",
                )
            db.session.commit()
            imported.append(message)

    return imported


def ensure_instance_webhook(instance):
    if not instance:
        return None

    if not instance.webhook_secret:
        instance.webhook_secret = secrets.token_urlsafe(24)
        db.session.commit()

    response = requests.post(
        f"{EVOLUTION_BASE_URL}/webhook/set/{instance.instance_name}",
        json={
            "webhook": {
                "url": INTERNAL_WEBHOOK_URL,
                "enabled": True,
                "webhookByEvents": False,
                "webhookBase64": False,
                "events": ["MESSAGES_UPSERT", "CONNECTION_UPDATE"],
                "headers": {
                    "X-Webhook-Secret": instance.webhook_secret,
                },
            }
        },
        headers={"apikey": EVOLUTION_API_KEY},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()
