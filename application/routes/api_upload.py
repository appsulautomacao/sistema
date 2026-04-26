from datetime import datetime
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile
import re

from flask import Blueprint, request, abort, send_from_directory, send_file, jsonify
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import os
import uuid

from models import Message, Conversation, MessageAttachment
from core.attachments import ensure_message_attachment
from core.attachment_storage import absolute_attachment_path, store_binary_content
from core.permissions import is_admin
from adapters.whatsapp.service import (
    decode_media_base64_payload,
    get_company_whatsapp_instance,
    get_media_base64,
)
from db import db

api_upload_bp = Blueprint("api_upload", __name__, url_prefix="/api")
media_download_bp = Blueprint("media_download", __name__)

UPLOAD_BASE = "uploads"
os.makedirs(UPLOAD_BASE, exist_ok=True)


def _assert_conversation_access(conversation):
    if conversation.company_id != current_user.company_id:
        abort(403)

    if not is_admin() and conversation.current_sector_id != current_user.sector_id:
        abort(403)


def _send_ready_attachment(attachment):
    full_path = absolute_attachment_path(attachment.storage_key)
    if not os.path.isfile(full_path):
        abort(404)

    attachment.downloaded_by_user_id = current_user.id
    attachment.downloaded_at = datetime.utcnow()
    db.session.commit()

    return send_file(
        full_path,
        as_attachment=True,
        download_name=attachment.original_filename or attachment.safe_filename or os.path.basename(full_path),
        mimetype=attachment.mime_type or "application/octet-stream",
    )


def _unique_archive_name(filename, used_names):
    safe_name = secure_filename(filename or "arquivo")
    if not safe_name:
        safe_name = "arquivo"

    if safe_name not in used_names:
        used_names.add(safe_name)
        return safe_name

    name, extension = os.path.splitext(safe_name)
    counter = 2
    while True:
        candidate = f"{name}_{counter}{extension}"
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate
        counter += 1


def _build_conversation_zip_name(conversation):
    raw_name = (
        conversation.client_name
        or conversation.client_phone
        or f"conversa_{conversation.id}"
    )
    normalized_name = secure_filename(str(raw_name).strip().lower().replace(" ", "_"))
    normalized_name = re.sub(r"_+", "_", normalized_name).strip("_") or f"conversa_{conversation.id}"

    timestamp_source = conversation.last_message_at or conversation.updated_at or conversation.created_at or datetime.utcnow()
    formatted_timestamp = timestamp_source.strftime("%d%m%Y_%H%M")

    return f"{normalized_name}_{formatted_timestamp}.zip"


def _materialize_provider_attachment(message, attachment=None):
    if not message.external_message_id:
        return None

    instance = get_company_whatsapp_instance(message.company_id or message.conversation.company_id)
    if not instance:
        return None

    payload = get_media_base64(
        instance,
        message.external_message_id,
        convert_to_mp4=(message.message_type == "video"),
    )
    content_bytes = decode_media_base64_payload(payload)

    original_filename = (
        (attachment.original_filename if attachment else None)
        or payload.get("fileName")
        or message.content
        or f"mensagem_{message.id}"
    )
    mime_type = (
        (attachment.mime_type if attachment else None)
        or payload.get("mimetype")
    )

    stored_media = store_binary_content(
        company_id=message.company_id or message.conversation.company_id,
        content_bytes=content_bytes,
        original_filename=original_filename,
        mime_type=mime_type,
        created_at=message.created_at or datetime.utcnow(),
    )

    materialized_attachment = ensure_message_attachment(
        message=message,
        attachment_type=message.message_type or message.type or "document",
        original_filename=stored_media.get("original_filename") or original_filename,
        provider="evolution",
        provider_message_id=message.external_message_id,
        provider_media_url=message.media_url,
        storage_key=stored_media.get("storage_key"),
        safe_filename=stored_media.get("safe_filename"),
        mime_type=stored_media.get("mime_type"),
        extension=stored_media.get("extension"),
        size_bytes=stored_media.get("size_bytes"),
        full_path=stored_media.get("full_path"),
        is_inbound=(message.sender_type == "client"),
        download_status="ready",
    )
    return materialized_attachment


def _resolve_message_attachment_file(message):
    attachment = MessageAttachment.query.filter_by(
        message_id=message.id,
    ).order_by(MessageAttachment.created_at.desc()).first()

    if attachment and attachment.storage_key:
        full_path = absolute_attachment_path(attachment.storage_key)
        if os.path.isfile(full_path):
            return attachment, full_path

    if (
        message.sender_type == "client"
        and message.external_message_id
        and (message.media_url or message.message_type in {"document", "image", "audio", "video"})
    ):
        materialized_attachment = _materialize_provider_attachment(message, attachment=attachment)
        if materialized_attachment and materialized_attachment.storage_key:
            full_path = absolute_attachment_path(materialized_attachment.storage_key)
            if os.path.isfile(full_path):
                return materialized_attachment, full_path

    if message.media_url:
        relative_path = message.media_url
        expected_prefix = f"company_{message.company_id or message.conversation.company_id}/"
        if (
            ".." not in relative_path
            and not relative_path.startswith("/")
            and relative_path.startswith(expected_prefix)
        ):
            uploads_root = os.path.join(os.getcwd(), "uploads")
            full_path = os.path.join(uploads_root, relative_path)
            if os.path.isfile(full_path):
                return attachment, full_path

    return attachment, None


# =========================
# UPLOAD
# =========================
@api_upload_bp.route("/upload", methods=["POST"])
@login_required
def upload_media():

    if "file" not in request.files:
        return {"error": "Nenhum arquivo enviado"}, 400

    file = request.files["file"]

    if file.filename == "":
        return {"error": "Nome inválido"}, 400

    original_filename = secure_filename(file.filename)
    extension = os.path.splitext(original_filename)[1]
    unique_name = f"{uuid.uuid4().hex}{extension}"

    company_folder = os.path.join(
        UPLOAD_BASE,
        f"company_{current_user.company_id}"
    )

    os.makedirs(company_folder, exist_ok=True)

    filepath = os.path.join(company_folder, unique_name)
    file.save(filepath)

    return {
        "media_path": f"company_{current_user.company_id}/{unique_name}",
        "original_filename": file.filename,
        "mime_type": file.mimetype,
    }


# =========================
# DOWNLOAD
# =========================
@api_upload_bp.route("/media/message/<int:message_id>")
@media_download_bp.route("/media/message/<int:message_id>")
@login_required
def download_media(message_id):

    message = Message.query.get_or_404(message_id)
    conversation = Conversation.query.get_or_404(message.conversation_id)
    _assert_conversation_access(conversation)

    attachment = MessageAttachment.query.filter_by(
        message_id=message.id,
    ).order_by(MessageAttachment.created_at.desc()).first()

    if attachment and attachment.storage_key:
        return _send_ready_attachment(attachment)

    if (
        message.sender_type == "client"
        and message.external_message_id
        and (message.media_url or message.message_type in {"document", "image", "audio", "video"})
    ):
        try:
            materialized_attachment = _materialize_provider_attachment(message, attachment=attachment)
            if materialized_attachment and materialized_attachment.storage_key:
                return _send_ready_attachment(materialized_attachment)
        except Exception as exc:
            print(f"Falha ao materializar anexo da Evolution para mensagem {message.id}: {exc}")

    if not message.media_url:
        abort(404)

    relative_path = message.media_url

    if ".." in relative_path or relative_path.startswith("/"):
        abort(403)

    expected_prefix = f"company_{current_user.company_id}/"

    if not relative_path.startswith(expected_prefix):
        abort(403)

    uploads_root = os.path.join(os.getcwd(), "uploads")
    full_path = os.path.join(uploads_root, relative_path)

    if not os.path.isfile(full_path):
        abort(404)

    return send_from_directory(
        uploads_root,
        relative_path,
        as_attachment=True
    )


@api_upload_bp.route("/attachments/<int:attachment_id>/download")
@media_download_bp.route("/attachments/<int:attachment_id>/download")
@login_required
def download_attachment(attachment_id):
    attachment = MessageAttachment.query.get_or_404(attachment_id)
    conversation = Conversation.query.get_or_404(attachment.conversation_id)
    _assert_conversation_access(conversation)

    if attachment.download_status == "ready" and attachment.storage_key:
        return _send_ready_attachment(attachment)

    message = Message.query.get_or_404(attachment.message_id)
    try:
        materialized_attachment = _materialize_provider_attachment(message, attachment=attachment)
        if materialized_attachment and materialized_attachment.storage_key:
            return _send_ready_attachment(materialized_attachment)
    except Exception as exc:
        print(f"Falha ao materializar anexo {attachment.id}: {exc}")

    abort(404)


@api_upload_bp.route("/conversations/<int:conversation_id>/attachments/download-zip", methods=["POST"])
@login_required
def download_conversation_attachments_zip(conversation_id):
    conversation = Conversation.query.filter_by(
        id=conversation_id,
        company_id=current_user.company_id,
    ).first_or_404()
    _assert_conversation_access(conversation)

    payload = request.get_json(silent=True) or {}
    requested_message_ids = payload.get("message_ids") or []
    requested_message_ids = [
        int(message_id)
        for message_id in requested_message_ids
        if str(message_id).isdigit()
    ]

    query = Message.query.filter(
        Message.conversation_id == conversation.id,
        Message.message_type.in_(["document", "image", "audio", "video"]),
    ).order_by(Message.created_at.asc(), Message.id.asc())

    if requested_message_ids:
        query = query.filter(Message.id.in_(requested_message_ids))

    messages = query.all()
    if not messages:
        return jsonify({"error": "Nenhum anexo selecionado"}), 400

    archive_buffer = BytesIO()
    used_names = set()
    included_count = 0

    with ZipFile(archive_buffer, "w", ZIP_DEFLATED) as archive:
        for message in messages:
            try:
                attachment, full_path = _resolve_message_attachment_file(message)
            except Exception as exc:
                print(f"Falha ao preparar anexo da mensagem {message.id} para zip: {exc}")
                continue

            if not full_path or not os.path.isfile(full_path):
                continue

            archive_name = _unique_archive_name(
                (attachment.original_filename if attachment else None)
                or message.content
                or os.path.basename(full_path),
                used_names,
            )
            archive.write(full_path, arcname=archive_name)
            included_count += 1

            if attachment:
                attachment.downloaded_by_user_id = current_user.id
                attachment.downloaded_at = datetime.utcnow()

    if not included_count:
        db.session.rollback()
        return jsonify({"error": "Nao foi possivel preparar os anexos selecionados"}), 400

    db.session.commit()
    archive_buffer.seek(0)

    zip_name = _build_conversation_zip_name(conversation)

    return send_file(
        archive_buffer,
        as_attachment=True,
        download_name=zip_name,
        mimetype="application/zip",
    )
