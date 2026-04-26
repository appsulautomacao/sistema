from flask import Blueprint, jsonify
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


@api_whatsapp_bp.route("/connect", methods=["POST"])
@login_required
def connect():
    denied = _admin_only()
    if denied:
        return denied

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

        return jsonify({
            "status": normalized_status,
            "instance": {
                "name": instance.instance_name,
                "state": normalized_status,
                "webhook_secret": instance.webhook_secret,
            },
            "raw_status": payload,
        })

    except Exception:
        return jsonify({"status": "error"})
