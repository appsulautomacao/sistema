from datetime import datetime, timezone
import os

import requests


PAGBANK_SANDBOX_BASE_URL = "https://sandbox.api.pagseguro.com"
PAGBANK_PRODUCTION_BASE_URL = "https://api.pagseguro.com"


def get_pagbank_base_url():
    configured = (os.getenv("PAGBANK_API_BASE_URL") or "").strip()
    if configured:
        return configured.rstrip("/")

    environment = (os.getenv("PAGBANK_ENVIRONMENT") or "sandbox").strip().lower()
    if environment == "production":
        return PAGBANK_PRODUCTION_BASE_URL
    return PAGBANK_SANDBOX_BASE_URL


def get_pagbank_api_token():
    return (os.getenv("PAGBANK_API_TOKEN") or "").strip()


def pagbank_is_configured():
    return bool(get_pagbank_api_token())


def _is_public_url(value):
    text = (value or "").strip().lower()
    if not text.startswith("https://"):
        return False
    if "localhost" in text or "127.0.0.1" in text:
        return False
    return True


def _build_payment_methods(session, plan):
    methods = []
    if plan.allow_card:
        methods.append({"type": "CREDIT_CARD"})
    if plan.allow_pix:
        methods.append({"type": "PIX"})
    if plan.allow_boleto:
        methods.append({"type": "BOLETO"})
    return methods


def _build_payment_methods_configs(session, plan):
    if session.payment_method != "card":
        return []

    return [
        {
            "type": "CREDIT_CARD",
            "config_options": [
                {
                    "option": "INSTALLMENTS_LIMIT",
                    "value": str(max(1, min(plan.max_installments or 1, session.installment_count or 1))),
                }
            ],
        }
    ]


def _build_recurrence_plan(plan):
    if plan.billing_period not in {"monthly", "yearly"}:
        return None

    return {
        "name": plan.name,
        "interval": {
            "unit": "MONTH",
            "length": 12 if plan.billing_period == "yearly" else 1,
        },
        "billing_cycles": 0,
    }


def build_pagbank_checkout_payload(session, plan, webhook_url=None, return_url=None):
    expires_at = session.expires_at
    expiration_value = None
    if expires_at:
        expiration_value = expires_at.replace(tzinfo=timezone.utc).astimezone().isoformat()

    payload = {
        "reference_id": session.public_token,
        "customer": {
            "name": session.admin_name,
            "email": session.admin_email,
        },
        "customer_modifiable": True,
        "items": [
            {
                "reference_id": plan.code,
                "name": plan.name,
                "quantity": 1,
                "unit_amount": session.amount_cents,
            }
        ],
        "payment_methods": _build_payment_methods(session, plan),
        "payment_methods_configs": _build_payment_methods_configs(session, plan),
        "notification_urls": [webhook_url] if webhook_url else [],
        "payment_notification_urls": [webhook_url] if webhook_url else [],
        "soft_descriptor": (os.getenv("PAGBANK_SOFT_DESCRIPTOR") or "APPSUL").strip()[:17],
    }

    if session.customer_document:
        payload["customer"]["tax_id"] = session.customer_document

    if expiration_value:
        payload["expiration_date"] = expiration_value

    effective_return_url = return_url if _is_public_url(return_url) else None
    if not effective_return_url and _is_public_url(session.success_url):
        effective_return_url = session.success_url

    if effective_return_url:
        payload["redirect_url"] = effective_return_url
        payload["return_url"] = effective_return_url

    recurrence_plan = _build_recurrence_plan(plan)
    if recurrence_plan and session.payment_method == "card":
        payload["recurrence_plan"] = recurrence_plan

    payload["notification_urls"] = [item for item in payload["notification_urls"] if item]
    payload["payment_notification_urls"] = [item for item in payload["payment_notification_urls"] if item]
    return payload


def create_pagbank_checkout(session, plan, webhook_url=None, return_url=None, timeout_seconds=25):
    token = get_pagbank_api_token()
    if not token:
        raise ValueError("PAGBANK_API_TOKEN nao configurado.")

    payload = build_pagbank_checkout_payload(
        session=session,
        plan=plan,
        webhook_url=webhook_url,
        return_url=return_url,
    )

    response = requests.post(
        f"{get_pagbank_base_url()}/checkouts",
        json=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=timeout_seconds,
    )

    try:
        data = response.json()
    except ValueError:
        data = {"raw_text": response.text}

    if response.status_code >= 400:
        raise ValueError(f"PagBank checkout error {response.status_code}: {data}")

    pay_url = None
    for link in data.get("links") or []:
        if link.get("rel") == "PAY":
            pay_url = link.get("href")
            break

    if not pay_url:
        raise ValueError("PagBank nao retornou link PAY para o checkout.")

    return {
        "provider_checkout_id": data.get("id"),
        "pay_url": pay_url,
        "payload": payload,
        "provider_response": data,
    }
