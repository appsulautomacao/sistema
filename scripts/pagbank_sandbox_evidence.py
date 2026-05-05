import argparse
import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import requests

from application import create_app
from core.commercial_service import create_checkout_session, ensure_default_billing_plans
from core.pagbank_service import build_pagbank_checkout_payload, get_pagbank_api_token, get_pagbank_base_url
from db import db


def _redact_headers(headers):
    redacted = dict(headers)
    if redacted.get("Authorization"):
        redacted["Authorization"] = "Bearer ***REDACTED***"
    return redacted


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False),
        encoding="utf-8",
    )


def _assert_sandbox():
    environment = (os.getenv("PAGBANK_ENVIRONMENT") or "").strip().lower()
    base_url = get_pagbank_base_url()
    if environment != "sandbox" or "sandbox.api.pagseguro.com" not in base_url:
        raise RuntimeError(
            "Este script deve ser executado em sandbox. "
            "Configure PAGBANK_ENVIRONMENT=sandbox e "
            "PAGBANK_API_BASE_URL=https://sandbox.api.pagseguro.com."
        )


def _create_case(method, plan_code, base_url, timestamp):
    installments = 12 if method == "card" else 1
    email = f"homologacao+{timestamp}-{method}@appsul.com.br"
    session = create_checkout_session(
        plan_code=plan_code,
        company_name=f"Appsul Homologacao PagBank {method.upper()}",
        admin_name="Homologacao PagBank",
        admin_email=email,
        customer_document="52998224725",
        payment_method=method,
        installment_count=installments,
        success_url=f"{base_url}/checkout/__token__/success",
        cancel_url=f"{base_url}/planos",
    )
    session.success_url = f"{base_url}/checkout/{session.public_token}/success"
    session.metadata_json = {
        **(session.metadata_json or {}),
        "success_url": session.success_url,
    }
    db.session.commit()
    return session


def _call_pagbank(session, base_url, timeout):
    token = get_pagbank_api_token()
    if not token:
        raise RuntimeError("PAGBANK_API_TOKEN nao configurado.")

    endpoint = f"{get_pagbank_base_url()}/checkouts"
    payload = build_pagbank_checkout_payload(
        session=session,
        plan=session.plan,
        webhook_url=f"{base_url}/webhooks/pagseguro",
        return_url=session.success_url,
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    started_at = datetime.now(timezone.utc).isoformat()
    response = requests.post(endpoint, json=payload, headers=headers, timeout=timeout)
    finished_at = datetime.now(timezone.utc).isoformat()

    try:
        response_json = response.json()
    except ValueError:
        response_json = {"raw_text": response.text}

    return {
        "started_at": started_at,
        "finished_at": finished_at,
        "endpoint": endpoint,
        "http_method": "POST",
        "request": {
            "headers": _redact_headers(headers),
            "body": payload,
        },
        "response": {
            "status_code": response.status_code,
            "headers": {
                "content-type": response.headers.get("content-type"),
                "x-request-id": response.headers.get("x-request-id"),
            },
            "body": response_json,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Gera evidencia de request/response PagBank em sandbox.")
    parser.add_argument("--plan-code", default="pro-monthly", help="Codigo do plano usado nos checkouts.")
    parser.add_argument("--base-url", default=os.getenv("PLATFORM_BASE_URL", "https://app.appsul.com.br"))
    parser.add_argument("--output", default="artifacts/pagbank_sandbox_evidence.json")
    parser.add_argument("--timeout", type=int, default=25)
    args = parser.parse_args()

    _assert_sandbox()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

    os.environ["BILLING_WORKER_ENABLED"] = "false"
    app = create_app()
    evidence = {
        "title": "Evidencia de homologacao PagBank - Checkout Sandbox",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "PAGBANK_ENVIRONMENT": os.getenv("PAGBANK_ENVIRONMENT"),
            "PAGBANK_API_BASE_URL": get_pagbank_base_url(),
            "PLATFORM_BASE_URL": args.base_url,
        },
        "payment_methods_tested": ["CREDIT_CARD", "PIX"],
        "cases": [],
    }

    with app.app_context():
        ensure_default_billing_plans()
        for method in ("card", "pix"):
            session = _create_case(method, args.plan_code, args.base_url.rstrip("/"), timestamp)
            case = _call_pagbank(session, args.base_url.rstrip("/"), args.timeout)
            case["application_checkout_session"] = {
                "public_token": session.public_token,
                "plan_code": session.plan.code,
                "payment_method": session.payment_method,
                "installment_count": session.installment_count,
                "amount_cents": session.amount_cents,
                "success_url": session.success_url,
            }
            evidence["cases"].append(case)

    output_path = Path(args.output)
    _write_json(output_path, deepcopy(evidence))
    print(f"Evidencia gerada em: {output_path}")
    for case in evidence["cases"]:
        print(
            f"{case['application_checkout_session']['payment_method']}: "
            f"HTTP {case['response']['status_code']}"
        )


if __name__ == "__main__":
    main()
