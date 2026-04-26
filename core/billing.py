import hashlib
import json


APPROVED_PAYMENT_STATUSES = {
    "paid",
    "approved",
    "authorized",
    "completed",
}


def _get_nested(payload, *path):
    current = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def normalize_pagseguro_payload(payload):
    payload = payload or {}

    metadata = _get_nested(payload, "metadata") or {}
    customer = _get_nested(payload, "customer") or {}
    payer = _get_nested(payload, "payer") or {}
    charges = _get_nested(payload, "charges") or []
    first_charge = charges[0] if isinstance(charges, list) and charges else {}

    external_event_id = (
        payload.get("id")
        or payload.get("notificationCode")
        or payload.get("eventId")
        or _get_nested(payload, "transaction", "id")
        or _get_nested(first_charge, "id")
    )
    event_type = payload.get("type") or payload.get("eventType")
    payment_status = (
        payload.get("status")
        or _get_nested(first_charge, "status")
        or _get_nested(payload, "transaction", "status")
    )
    reference = (
        payload.get("reference")
        or payload.get("reference_id")
        or _get_nested(payload, "transaction", "reference")
        or metadata.get("reference")
    )
    checkout_session_token = (
        metadata.get("checkout_session_token")
        or metadata.get("checkout_token")
        or payload.get("checkout_session_token")
    )
    plan_code = (
        metadata.get("plan_code")
        or payload.get("plan_code")
    )
    billing_period = (
        metadata.get("billing_period")
        or payload.get("billing_period")
    )
    payment_method = (
        metadata.get("payment_method")
        or payload.get("payment_method")
        or _get_nested(first_charge, "payment_method", "type")
        or _get_nested(payload, "paymentMethod", "type")
    )
    installment_count = (
        metadata.get("installment_count")
        or payload.get("installment_count")
        or _get_nested(first_charge, "payment_method", "installments")
        or _get_nested(payload, "paymentMethod", "installments")
    )
    amount_value = (
        payload.get("amount")
        or payload.get("amount_value")
        or _get_nested(first_charge, "amount", "value")
        or _get_nested(payload, "transaction", "grossAmount")
    )
    amount_cents = None
    if amount_value is not None and amount_value != "":
        try:
            amount_cents = int(round(float(str(amount_value).replace(",", ".")) * 100))
        except (TypeError, ValueError):
            amount_cents = None

    company_name = (
        metadata.get("company_name")
        or metadata.get("company")
        or payload.get("company_name")
        or reference
    )
    admin_name = (
        metadata.get("admin_name")
        or customer.get("name")
        or payer.get("name")
        or "Admin"
    )
    admin_email = (
        metadata.get("admin_email")
        or customer.get("email")
        or payer.get("email")
        or payload.get("email")
    )

    normalized_installment_count = None
    if installment_count not in (None, ""):
        try:
            normalized_installment_count = int(installment_count)
        except (TypeError, ValueError):
            normalized_installment_count = None

    normalized = {
        "provider": "pagseguro",
        "external_event_id": str(external_event_id) if external_event_id else None,
        "event_type": str(event_type) if event_type else None,
        "payment_status": str(payment_status).lower() if payment_status else None,
        "reference": str(reference) if reference else None,
        "checkout_session_token": str(checkout_session_token) if checkout_session_token else None,
        "plan_code": str(plan_code).strip() if plan_code else None,
        "billing_period": str(billing_period).strip().lower() if billing_period else None,
        "payment_method": str(payment_method).strip().lower() if payment_method else None,
        "installment_count": normalized_installment_count,
        "amount_cents": amount_cents,
        "company_name": str(company_name).strip() if company_name else None,
        "admin_name": str(admin_name).strip() if admin_name else "Admin",
        "admin_email": str(admin_email).strip().lower() if admin_email else None,
        "raw_payload": payload,
    }
    return normalized


def build_billing_dedupe_key(provider, external_event_id, payload):
    if external_event_id:
        return f"{provider}:{external_event_id}"

    payload_dump = json.dumps(payload or {}, sort_keys=True, ensure_ascii=True)
    payload_hash = hashlib.sha256(payload_dump.encode("utf-8")).hexdigest()
    return f"{provider}:payload:{payload_hash}"


def is_payment_approved(payment_status):
    if not payment_status:
        return False
    return str(payment_status).strip().lower() in APPROVED_PAYMENT_STATUSES
