import os
from importlib import metadata

from db import db
from extensions import socketio
from models import CompanySettings
from models import ConversationHistory
from models import Sector
from core.conversation_cycles import get_conversation_cycle_messages
from core.conversation_cycles import get_conversation_cycle_started_at
from core.rag import search_company_rag
from core.datetime_utils import serialize_utc
from core.history import log_conversation_event
from core.messages import create_message
from adapters.whatsapp.service import send_text_message


DEFAULT_ASSISTANT_PROMPT = (
    "Voce e um assistente virtual de pre-atendimento da central de atendimento. "
    "Atue como uma recepcao inteligente, humana e profissional no WhatsApp. "
    "Responda em portugues do Brasil, com tom natural, objetivo e cordial. "
    "Evite linguagem robotica, formalidade excessiva, despedidas repetitivas e assinaturas padrao "
    "como 'Atenciosamente' ou 'Central de Atendimento' em toda mensagem. "
    "Use apenas informacoes confirmadas no contexto da empresa e nunca invente preco, prazo, politica, "
    "desconto, condicao comercial ou regra operacional.\n\n"
    "Limites operacionais:\n"
    "- voce pode tirar duvidas gerais, acolher o cliente e coletar informacoes iniciais\n"
    "- voce pode usar o contexto da base da empresa para orientar o pre-atendimento\n"
    "- voce nao deve fechar orcamento, proposta comercial, desconto ou condicao final\n"
    "- quando o cliente pedir orcamento, proposta, valor personalizado ou algo que dependa de avaliacao humana, "
    "colete os dados essenciais e informe de forma natural que vai encaminhar para o setor de Orcamento montar a proposta\n"
    "- quando faltar base suficiente, deixe isso claro e oriente o proximo passo sem inventar\n"
    "- se houver necessidade de outro setor, sinalize o encaminhamento de forma simples e humana"
)
AUTO_REPLY_MIN_CHARS = 3
AUTO_REPLY_MAX_CHARS = 450


def _call_openai_messages(api_key, model, messages, temperature=0.2):
    modern_error = None

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=messages,
        )
        return response.choices[0].message.content or "", "openai-modern"
    except Exception as exc:
        modern_error = exc

    try:
        openai_version = metadata.version("openai")
    except metadata.PackageNotFoundError:
        openai_version = ""

    if not openai_version.startswith("0."):
        raise modern_error or RuntimeError("openai_modern_call_failed")

    try:
        import openai

        openai.api_key = api_key
        response = openai.ChatCompletion.create(
            model=model,
            temperature=temperature,
            messages=messages,
        )
        return response.choices[0].message["content"] or "", "openai-legacy"
    except Exception:
        raise modern_error or RuntimeError("openai_legacy_call_failed")


def get_company_assistant_settings(company_id):
    return CompanySettings.query.filter_by(company_id=company_id).first()


def _conversation_has_ai_auto_reply(conversation_id):
    cycle_started_at = get_conversation_cycle_started_at(conversation_id)

    query = ConversationHistory.query.filter_by(
        conversation_id=conversation_id,
        action_type="ai_auto_reply",
    )
    if cycle_started_at:
        query = query.filter(ConversationHistory.created_at >= cycle_started_at)

    return query.first() is not None


def _normalize_ai_reply(reply):
    cleaned = " ".join(str(reply or "").strip().split())
    return cleaned[:AUTO_REPLY_MAX_CHARS].strip()


def _prepare_customer_visible_ai_reply(conversation, reply):
    normalized_reply = _normalize_ai_reply(reply)
    if not normalized_reply:
        return ""

    if _conversation_has_ai_auto_reply(conversation.id):
        return normalized_reply

    intro = "Oi, sou a assistente virtual da central e vou te ajudar por aqui. "
    combined = f"{intro}{normalized_reply}".strip()
    if len(combined) <= AUTO_REPLY_MAX_CHARS:
        return combined

    remaining = max(0, AUTO_REPLY_MAX_CHARS - len(intro))
    return f"{intro}{normalized_reply[:remaining].strip()}".strip()


def build_company_assistant_messages(company_id, customer_message, conversation_messages=None):
    settings = get_company_assistant_settings(company_id)
    assistant_model = (
        (settings.ai_assistant_model if settings and settings.ai_assistant_model else None)
        or os.getenv("OPENAI_ASSISTANT_MODEL")
        or "gpt-4o-mini"
    )
    assistant_prompt = (
        (settings.ai_assistant_prompt if settings and settings.ai_assistant_prompt else "").strip()
        or DEFAULT_ASSISTANT_PROMPT
    )

    rag_result = search_company_rag(company_id, customer_message, limit=4)
    rag_context = "\n\n".join(
        f"[Trecho {item['index']} | score {item['score']}]\n{item['content']}"
        for item in rag_result.get("results", [])
    ).strip()

    history_lines = []
    for message in conversation_messages or []:
        sender = message.get("sender") or message.get("sender_type") or "desconhecido"
        content = (message.get("content") or "").strip()
        if content:
            history_lines.append(f"{sender}: {content}")
    conversation_context = "\n".join(history_lines[-8:]).strip()

    user_prompt = (
        "Crie uma sugestao de resposta para o cliente.\n\n"
        f"Mensagem atual do cliente:\n{customer_message.strip()}\n\n"
        f"Historico recente:\n{conversation_context or 'Sem historico relevante.'}\n\n"
        f"Contexto da base da empresa:\n{rag_context or 'Sem contexto recuperado no RAG.'}\n\n"
        "Objetivo:\n"
        "- responder em portugues do Brasil\n"
        "- soar humano, cordial e profissional\n"
        "- evitar assinatura fixa e encerramentos repetitivos\n"
        "- escrever de forma curta e natural para WhatsApp\n"
        "- responder em no maximo 3 frases curtas\n"
        "- preferir uma unica mensagem enxuta, sem blocos longos\n"
        "- ficar idealmente abaixo de 450 caracteres\n"
        "- usar somente informacoes confirmadas\n"
        "- se faltar dado, orientar o proximo passo sem inventar\n"
        "- se for pedido de orcamento, nao passar valor inventado nem proposta pronta\n"
        "- em pedidos de orcamento, coletar o essencial e informar que vai encaminhar para o setor de Orcamento montar a proposta\n"
        "- se precisar de outro setor, deixar o encaminhamento claro de forma natural"
    )

    return {
        "model": assistant_model,
        "messages": [
            {"role": "system", "content": assistant_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "rag_result": rag_result,
    }


def generate_company_assistant_reply(company_id, customer_message, conversation_messages=None):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {
            "reply": "",
            "provider": "fallback",
            "model": "",
            "reason": "missing_openai_api_key",
            "rag_result": {"configured_path": None, "results": []},
        }

    payload = build_company_assistant_messages(
        company_id=company_id,
        customer_message=customer_message,
        conversation_messages=conversation_messages,
    )

    try:
        reply, provider = _call_openai_messages(
            api_key=api_key,
            model=payload["model"],
            messages=payload["messages"],
            temperature=0.2,
        )
        return {
            "reply": reply.strip(),
            "provider": provider,
            "model": payload["model"],
            "reason": "",
            "rag_result": payload["rag_result"],
            "messages": payload["messages"],
        }
    except Exception as exc:
        return {
            "reply": "",
            "provider": "fallback",
            "model": payload["model"],
            "reason": str(exc),
            "rag_result": payload["rag_result"],
            "messages": payload["messages"],
        }


def should_auto_reply_in_central(conversation, inbound_message=None):
    if not conversation:
        return False, "missing_conversation"

    settings = get_company_assistant_settings(conversation.company_id)
    if not settings or not settings.central_ai_enabled:
        return False, "central_ai_disabled"

    current_sector = db.session.get(Sector, conversation.current_sector_id) if conversation.current_sector_id else None
    if not current_sector or not current_sector.is_central:
        return False, "conversation_not_in_central"

    if conversation.assigned_to:
        return False, "conversation_assigned"

    if inbound_message and (inbound_message.sender_type or inbound_message.sender) != "client":
        return False, "message_not_from_client"

    content = (inbound_message.content if inbound_message else "") or ""
    if len(content.strip()) < AUTO_REPLY_MIN_CHARS:
        return False, "message_too_short"

    return True, ""


def auto_reply_to_central_conversation(instance, conversation, inbound_message):
    allowed, reason = should_auto_reply_in_central(conversation, inbound_message)
    if not allowed:
        return {"sent": False, "reason": reason}

    conversation_messages = [
        message.to_dict()
        for message in get_conversation_cycle_messages(conversation.id)
    ]

    result = generate_company_assistant_reply(
        company_id=conversation.company_id,
        customer_message=(inbound_message.content or "").strip(),
        conversation_messages=conversation_messages,
    )

    reply = _prepare_customer_visible_ai_reply(
        conversation,
        (result.get("reply") or "").strip(),
    )
    if not reply:
        return {
            "sent": False,
            "reason": result.get("reason") or "empty_ai_reply",
            "assistant_result": result,
        }

    external_response = send_text_message(
        instance,
        conversation.client_phone,
        reply,
    )

    resolved_remote_jid = external_response.get("key", {}).get("remoteJid")
    if resolved_remote_jid and conversation.client_phone != resolved_remote_jid:
        conversation.client_phone = resolved_remote_jid
        db.session.commit()

    external_message_id = (
        external_response.get("key", {}).get("id")
        or external_response.get("id")
    )

    auto_message = create_message(
        conversation_id=conversation.id,
        sender_type="agent",
        content=reply,
        message_type="text",
        external_message_id=external_message_id,
    )

    log_conversation_event(
        conversation=conversation,
        event_type="ai_auto_reply",
        sector_id=conversation.current_sector_id,
        metadata={
            "provider": result.get("provider"),
            "model": result.get("model"),
            "reason": result.get("reason"),
            "rag_context_count": len((result.get("rag_result") or {}).get("results", [])),
        },
    )

    socketio.emit(
        "new_message",
        {
            "id": auto_message.id,
            "conversation_id": auto_message.conversation_id,
            "sender": auto_message.sender_type,
            "content": auto_message.content,
            "type": auto_message.message_type,
            "media_url": auto_message.media_url,
            "attachments": [attachment.to_dict() for attachment in auto_message.attachments],
            "created_at": serialize_utc(auto_message.created_at),
        },
        room=f"conversation_{auto_message.conversation_id}",
    )

    return {
        "sent": True,
        "reason": "",
        "assistant_result": result,
        "message_id": auto_message.id,
    }
