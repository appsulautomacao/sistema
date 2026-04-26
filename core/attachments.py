from datetime import datetime, timedelta
from mimetypes import guess_type
import hashlib
import os

from db import db
from models import MessageAttachment


DEFAULT_RETENTION_DAYS = {
    "image": 180,
    "document": 180,
    "spreadsheet": 180,
    "audio": 90,
    "video": 60,
    "archive": 60,
    "unknown": 90,
}


def infer_attachment_type(message_type=None, filename=None, mime_type=None):
    message_type = (message_type or "").lower()
    mime_type = (mime_type or "").lower()
    extension = os.path.splitext(filename or "")[1].lower()

    if message_type in {"image", "audio", "video", "document"}:
        if message_type == "document" and extension in {".xls", ".xlsx", ".csv"}:
            return "spreadsheet"
        return message_type

    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("audio/"):
        return "audio"
    if mime_type.startswith("video/"):
        return "video"
    if extension in {".xls", ".xlsx", ".csv"}:
        return "spreadsheet"
    if extension in {".zip", ".rar", ".7z"}:
        return "archive"
    if extension in {".pdf", ".doc", ".docx", ".txt", ".ppt", ".pptx"}:
        return "document"
    return "unknown"


def _build_expiration(attachment_type, created_at=None):
    created_at = created_at or datetime.utcnow()
    days = DEFAULT_RETENTION_DAYS.get(attachment_type, 90)
    return created_at + timedelta(days=days)


def _checksum(full_path):
    if not full_path or not os.path.isfile(full_path):
        return None

    digest = hashlib.sha256()
    with open(full_path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_message_attachment(
    message,
    attachment_type,
    original_filename=None,
    provider=None,
    provider_message_id=None,
    provider_media_url=None,
    storage_backend="local",
    storage_key=None,
    safe_filename=None,
    mime_type=None,
    extension=None,
    size_bytes=None,
    full_path=None,
    is_inbound=True,
    download_status=None,
):
    mime_type = mime_type or guess_type(original_filename or "")[0]
    attachment_type = infer_attachment_type(
        message_type=attachment_type,
        filename=original_filename,
        mime_type=mime_type,
    )
    existing = None
    if provider_message_id:
        existing = MessageAttachment.query.filter_by(
            message_id=message.id,
            provider_message_id=provider_message_id,
        ).first()
    if not existing and storage_key:
        existing = MessageAttachment.query.filter_by(
            message_id=message.id,
            storage_key=storage_key,
        ).first()
    if not existing and provider_media_url:
        existing = MessageAttachment.query.filter_by(
            message_id=message.id,
            provider_media_url=provider_media_url,
        ).first()
    if existing:
        updated = False
        if provider and existing.provider != provider:
            existing.provider = provider
            updated = True
        if provider_media_url and existing.provider_media_url != provider_media_url:
            existing.provider_media_url = provider_media_url
            updated = True
        if original_filename and not existing.original_filename:
            existing.original_filename = original_filename
            updated = True
        if safe_filename and not existing.safe_filename:
            existing.safe_filename = safe_filename
            updated = True
        if mime_type and not existing.mime_type:
            existing.mime_type = mime_type
            updated = True
        if extension and not existing.extension:
            existing.extension = extension
            updated = True
        if size_bytes and not existing.size_bytes:
            existing.size_bytes = size_bytes
            updated = True
        if storage_key and existing.storage_key != storage_key:
            existing.storage_key = storage_key
            existing.storage_backend = storage_backend
            existing.download_status = download_status or "ready"
            existing.processed_at = datetime.utcnow()
            updated = True
        if full_path and not existing.checksum_sha256:
            existing.checksum_sha256 = _checksum(full_path)
            updated = True
        if updated:
            db.session.commit()
        return existing

    status = download_status or ("ready" if storage_key else "pending")
    processed_at = datetime.utcnow() if status == "ready" else None

    attachment = MessageAttachment(
        message_id=message.id,
        conversation_id=message.conversation_id,
        company_id=message.company_id or (message.conversation.company_id if message.conversation else None),
        provider=provider,
        provider_message_id=provider_message_id,
        provider_media_url=provider_media_url,
        storage_backend=storage_backend,
        storage_key=storage_key,
        original_filename=original_filename,
        safe_filename=safe_filename,
        mime_type=mime_type,
        extension=extension,
        size_bytes=size_bytes,
        checksum_sha256=_checksum(full_path),
        attachment_type=attachment_type,
        download_status=status,
        is_inbound=is_inbound,
        expires_at=_build_expiration(attachment_type),
        processed_at=processed_at,
    )
    db.session.add(attachment)
    db.session.commit()
    return attachment
