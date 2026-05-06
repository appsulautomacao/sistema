from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required
import requests
import time

from adapters.whatsapp.service import (
    EVOLUTION_API_KEY,
    EVOLUTION_BASE_URL,
    create_company_whatsapp_instance,
    ensure_instance_webhook,
    get_company_whatsapp_instance,
    normalize_evolution_status,
    sync_instance_status,
    update_instance_status,
)
from core.whatsapp_authorization import (
    get_authorized_whatsapp_number,
    normalize_whatsapp_number,
    numbers_match,
    set_authorized_whatsapp_number,
)


api_whatsapp_bp = Blueprint("api_whatsapp", __name__, url_prefix="/api/whatsapp")


def _admin_only():
    if current_user.role != "ADMIN":
        return jsonify({"error": "Acesso negado"}), 403
    return None


def _extract_qr_base64(payload):
    if not isinstance(payload, dict):
        return None

    if payload.get("base64"):
        return payload.get("base64")

    qrcode = payload.get("qrcode")
    if isinstance(qrcode, dict) and qrcode.get("base64"):
        return qrcode.get("base64")

    if isinstance(qrcode, str) and qrcode.strip():
        return qrcode

    return None


def _extract_connected_number(payload):
    if not isinstance(payload, dict):
        return None

    keys = (
        "ownerJid",
        "owner",
        "number",
        "phone",
        "profileId",
        "wuid",
        "jid",
    )
    for key in keys:
        value = payload.get(key)
        normalized = normalize_whatsapp_number(value)
        if normalized:
            return normalized

    for value in payload.values():
        if isinstance(value, dict):
            nested = _extract_connected_number(value)
            if nested:
                return nested
        elif isinstance(value, list):
            for item in value:
                nested = _extract_connected_number(item)
                if nested:
                    return nested

    return None


def _fetch_connected_number(instance):
    payloads = []
    try:
        response = requests.get(
            f"{EVOLUTION_BASE_URL}/instance/connectionState/{instance.instance_name}",
            headers={"apikey": EVOLUTION_API_KEY},
            timeout=15,
        )
        payloads.append(response.json() if response.content else {})
    except Exception:
        pass

    try:
        response = requests.get(
            f"{EVOLUTION_BASE_URL}/instance/fetchInstances",
            headers={"apikey": EVOLUTION_API_KEY},
            timeout=20,
        )
        payloads.append(response.json() if response.content else {})
    except Exception:
        pass

    for payload in payloads:
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict) and item.get("instanceName") == instance.instance_name:
                    number = _extract_connected_number(item)
                    if number:
                        return number
        if isinstance(payload, dict):
            instances = payload.get("instances")
            if isinstance(instances, list):
                for item in instances:
                    if isinstance(item, dict) and item.get("instanceName") == instance.instance_name:
                        number = _extract_connected_number(item)
                        if number:
                            return number

    for payload in payloads:
        number = _extract_connected_number(payload)
        if number:
            return number
    return None


def _disconnect_instance(instance):
    requests.delete(
        f"{EVOLUTION_BASE_URL}/instance/delete/{instance.instance_name}",
        headers={"apikey": EVOLUTION_API_KEY},
        timeout=20,
    )
    update_instance_status(instance, "deleted")


@api_whatsapp_bp.route("/authorized-number", methods=["POST"])
@login_required
def authorized_number():
    denied = _admin_only()
    if denied:
        return denied

    existing = get_authorized_whatsapp_number(current_user.company_id)
    if existing:
        return jsonify({"number": existing, "locked": True})

    payload = request.get_json(silent=True) if request.is_json else {}
    submitted_number = request.form.get("whatsapp_number") or (payload or {}).get("whatsapp_number")

    try:
        number = set_authorized_whatsapp_number(current_user.company_id, submitted_number)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({"number": number, "locked": False})


@api_whatsapp_bp.route("/connect", methods=["POST"])
@login_required
def connect():
    denied = _admin_only()
    if denied:
        return denied

    authorized = get_authorized_whatsapp_number(current_user.company_id)
    if not authorized:
        return jsonify({"error": "Informe o WhatsApp autorizado da empresa antes de conectar."}), 400

    instance = get_company_whatsapp_instance(current_user.company_id)
    if instance:
        return jsonify({"status": "already_exists"})

    try:
        create_company_whatsapp_instance(current_user.company_id)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify({"status": "created"})


@api_whatsapp_bp.route("/qrcode")
@login_required
def qrcode():
    denied = _admin_only()
    if denied:
        return denied

    authorized = get_authorized_whatsapp_number(current_user.company_id)
    if not authorized:
        return jsonify({"error": "Informe o WhatsApp autorizado da empresa antes de gerar o QR Code."}), 400

    instance = get_company_whatsapp_instance(current_user.company_id)
    if not instance:
        try:
            instance, _ = create_company_whatsapp_instance(current_user.company_id)
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 500

    try:
        ensure_instance_webhook(instance)
    except Exception as exc:
        return jsonify({"error": f"webhook_setup_failed: {exc}"}, 500)

    qr_base64 = None
    last_payload = None

    for _ in range(8):
        response = requests.get(
            f"{EVOLUTION_BASE_URL}/instance/connect/{instance.instance_name}",
            headers={"apikey": EVOLUTION_API_KEY},
            timeout=15,
        )

        payload = response.json() if response.content else {}
        last_payload = payload
        qr_base64 = _extract_qr_base64(payload)

        if qr_base64:
            break

        time.sleep(1)

    return jsonify({"qr": qr_base64, "raw": last_payload})


@api_whatsapp_bp.route("/status")
@login_required
def status():
    denied = _admin_only()
    if denied:
        return denied

    instance = get_company_whatsapp_instance(current_user.company_id)
    if not instance:
        return jsonify({"status": "disconnected"})

    try:
        ensure_instance_webhook(instance)
        resp = requests.get(
            f"{EVOLUTION_BASE_URL}/instance/connectionState/{instance.instance_name}",
            headers={"apikey": EVOLUTION_API_KEY}
        )
        payload = resp.json()
        sync_instance_status(instance, payload)
        normalized_status = normalize_evolution_status(payload)
        authorized = get_authorized_whatsapp_number(current_user.company_id)
        connected_number = _fetch_connected_number(instance) if normalized_status == "open" else None

        if normalized_status == "open" and authorized and connected_number and not numbers_match(authorized, connected_number):
            _disconnect_instance(instance)
            return jsonify({
                "status": "blocked_wrong_number",
                "authorized_number": authorized,
                "connected_number": connected_number,
                "error": "O WhatsApp conectado nao e o numero autorizado para esta empresa.",
            }), 409

        return jsonify({
            "status": normalized_status,
            "authorized_number": authorized,
            "connected_number": connected_number,
            "instance": {
                "name": instance.instance_name,
                "state": normalized_status,
                "webhook_secret": instance.webhook_secret,
            },
            "raw_status": payload,
        })

    except Exception:
        return jsonify({"status": "error"})
