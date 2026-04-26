import os
import uuid
from datetime import datetime
from mimetypes import guess_type

from werkzeug.utils import secure_filename


ATTACHMENTS_BASE = "storage"


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def get_company_attachment_dir(company_id, created_at=None):
    created_at = created_at or datetime.utcnow()
    return _ensure_dir(
        os.path.join(
            ATTACHMENTS_BASE,
            f"company_{company_id}",
            "attachments",
            created_at.strftime("%Y"),
            created_at.strftime("%m"),
            created_at.strftime("%d"),
        )
    )


def build_attachment_storage_key(company_id, original_filename=None, created_at=None):
    created_at = created_at or datetime.utcnow()
    original_filename = secure_filename(original_filename or "arquivo")
    name, extension = os.path.splitext(original_filename)
    safe_name = secure_filename(name) or "arquivo"
    unique_name = f"{uuid.uuid4().hex}_{safe_name}{extension.lower()}"
    relative_dir = os.path.join(
        f"company_{company_id}",
        "attachments",
        created_at.strftime("%Y"),
        created_at.strftime("%m"),
        created_at.strftime("%d"),
    )
    storage_key = os.path.join(relative_dir, unique_name).replace("\\", "/")
    return storage_key, unique_name, extension.lower()


def absolute_attachment_path(storage_key):
    return os.path.join(os.getcwd(), ATTACHMENTS_BASE, storage_key.replace("/", os.sep))


def store_filestorage(company_id, file_storage, created_at=None):
    created_at = created_at or datetime.utcnow()
    storage_key, safe_filename, extension = build_attachment_storage_key(
        company_id,
        original_filename=file_storage.filename,
        created_at=created_at,
    )
    full_path = absolute_attachment_path(storage_key)
    _ensure_dir(os.path.dirname(full_path))
    file_storage.save(full_path)
    size_bytes = os.path.getsize(full_path)
    mime_type = file_storage.mimetype or guess_type(file_storage.filename or "")[0]
    return {
        "storage_key": storage_key,
        "safe_filename": safe_filename,
        "extension": extension,
        "mime_type": mime_type,
        "size_bytes": size_bytes,
        "full_path": full_path,
    }


def store_binary_content(company_id, content_bytes, original_filename=None, mime_type=None, created_at=None):
    created_at = created_at or datetime.utcnow()
    storage_key, safe_filename, extension = build_attachment_storage_key(
        company_id,
        original_filename=original_filename,
        created_at=created_at,
    )
    full_path = absolute_attachment_path(storage_key)
    _ensure_dir(os.path.dirname(full_path))

    with open(full_path, "wb") as target_handle:
        target_handle.write(content_bytes)

    size_bytes = os.path.getsize(full_path)
    resolved_mime_type = mime_type or guess_type(original_filename or "")[0]
    return {
        "storage_key": storage_key,
        "safe_filename": safe_filename,
        "extension": extension,
        "mime_type": resolved_mime_type,
        "size_bytes": size_bytes,
        "full_path": full_path,
        "original_filename": original_filename,
    }


def register_existing_upload(company_id, relative_path):
    full_path = os.path.join(os.getcwd(), "uploads", relative_path.replace("/", os.sep))
    if not os.path.isfile(full_path):
        raise FileNotFoundError(full_path)

    original_filename = os.path.basename(relative_path)
    storage_key, safe_filename, extension = build_attachment_storage_key(
        company_id,
        original_filename=original_filename,
    )
    destination = absolute_attachment_path(storage_key)
    _ensure_dir(os.path.dirname(destination))

    with open(full_path, "rb") as source_handle:
        with open(destination, "wb") as target_handle:
            target_handle.write(source_handle.read())

    mime_type = guess_type(original_filename)[0]
    size_bytes = os.path.getsize(destination)
    return {
        "storage_key": storage_key,
        "safe_filename": safe_filename,
        "extension": extension,
        "mime_type": mime_type,
        "size_bytes": size_bytes,
        "full_path": destination,
        "original_filename": original_filename,
    }
