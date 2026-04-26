from flask import Blueprint, redirect, render_template, url_for
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
from models import Company
from flask import abort


admin_whatsapp_bp = Blueprint(
    "admin_whatsapp",
    __name__,
    url_prefix="/admin/whatsapp"
)


@admin_whatsapp_bp.route("/")
@login_required
def whatsapp_page():
    if current_user.role != "ADMIN":
        return abort(403)

    company = Company.query.get(current_user.company_id)
    instance = get_company_whatsapp_instance(current_user.company_id)
    return render_template(
        "admin/whatsapp.html",
        company=company,
        whatsapp_instance=instance,
    )


@admin_whatsapp_bp.route("/connect")
@login_required
def connect_whatsapp():
    if current_user.role != "ADMIN":
        return abort(403)

    instance = get_company_whatsapp_instance(current_user.company_id)
    if instance:
        return redirect(url_for("admin_whatsapp.qrcode"))

    try:
        create_company_whatsapp_instance(current_user.company_id)
    except RuntimeError as exc:
        return f"Erro ao criar instância: {exc}"

    return redirect(url_for("admin_whatsapp.qrcode"))


@admin_whatsapp_bp.route("/qrcode")
@login_required
def qrcode():
    if current_user.role != "ADMIN":
        return abort(403)

    instance = get_company_whatsapp_instance(current_user.company_id)
    if not instance:
        return redirect(url_for("admin_whatsapp.connect_whatsapp"))

    ensure_instance_webhook(instance)

    status_resp = requests.get(
        f"{EVOLUTION_BASE_URL}/instance/connectionState/{instance.instance_name}",
        headers={"apikey": EVOLUTION_API_KEY}
    )
    status = status_resp.json()

    if status == "open":
        update_instance_status(instance, "open")
        return redirect("/dashboard")

    requests.get(
        f"{EVOLUTION_BASE_URL}/instance/connect/{instance.instance_name}",
        headers={"apikey": EVOLUTION_API_KEY}
    )

    time.sleep(2)

    response = requests.get(
        f"{EVOLUTION_BASE_URL}/instance/qrcode/{instance.instance_name}",
        headers={"apikey": EVOLUTION_API_KEY}
    )

    try:
        data = response.json()
    except Exception:
        return f"Erro bruto: {response.text}"

    qr_base64 = None

    for _ in range(10):
        response = requests.get(
            f"{EVOLUTION_BASE_URL}/instance/connect/{instance.instance_name}",
            headers={"apikey": EVOLUTION_API_KEY}
        )

        data = response.json()

        if "base64" in data:
            qr_base64 = data["base64"]
            break

        time.sleep(1)

    if not qr_base64:
        return f"""
        <h2>Gerando QR...</h2>
        <pre>{data}</pre>
        <meta http-equiv="refresh" content="2">
        """

    return f"""
    <h1>Escaneie o QR Code</h1>
    <img src="{qr_base64}" width="300">
    """


@admin_whatsapp_bp.route("/disconnect")
@login_required
def disconnect_whatsapp():
    if current_user.role != "ADMIN":
        return abort(403)

    instance = get_company_whatsapp_instance(current_user.company_id)
    if instance:
        requests.delete(
            f"{EVOLUTION_BASE_URL}/instance/delete/{instance.instance_name}",
            headers={"apikey": EVOLUTION_API_KEY}
        )
        update_instance_status(instance, "deleted")

    return redirect(url_for("admin_whatsapp.whatsapp_page"))


@admin_whatsapp_bp.route("/status")
@login_required
def whatsapp_status():
    if current_user.role != "ADMIN":
        return abort(403)

    instance = get_company_whatsapp_instance(current_user.company_id)
    if not instance:
        return {"status": "disconnected"}

    try:
        ensure_instance_webhook(instance)
        resp = requests.get(
            f"{EVOLUTION_BASE_URL}/instance/connectionState/{instance.instance_name}",
            headers={"apikey": EVOLUTION_API_KEY}
        )
        payload = resp.json()
        sync_instance_status(instance, payload)
        normalized_status = normalize_evolution_status(payload)

        return {
            "status": normalized_status,
            "instance": {
                "name": instance.instance_name,
                "state": normalized_status,
                "webhook_secret": instance.webhook_secret,
            },
            "raw_status": payload,
        }

    except Exception:
        return {"status": "error"}
