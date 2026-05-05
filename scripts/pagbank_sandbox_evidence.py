import argparse
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests


SANDBOX_BASE_URL = "https://sandbox.api.pagseguro.com"


def _now():
    return datetime.now(timezone.utc)


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False),
        encoding="utf-8",
    )


def _redact_headers(headers):
    redacted = dict(headers)
    if redacted.get("Authorization"):
        redacted["Authorization"] = "Bearer ***REDACTED***"
    return redacted


def _sandbox_config():
    environment = (os.getenv("PAGBANK_ENVIRONMENT") or "").strip().lower()
    base_url = (os.getenv("PAGBANK_API_BASE_URL") or SANDBOX_BASE_URL).strip().rstrip("/")
    token = (os.getenv("PAGBANK_API_TOKEN") or "").strip().strip("'\"")

    if environment != "sandbox" or "sandbox.api.pagseguro.com" not in base_url:
        raise RuntimeError(
            "Configure PAGBANK_ENVIRONMENT=sandbox e "
            "PAGBANK_API_BASE_URL=https://sandbox.api.pagseguro.com antes de gerar a evidencia."
        )
    if not token:
        raise RuntimeError("PAGBANK_API_TOKEN nao configurado.")

    return base_url, token


def _checkout_payload(payment_method, base_url, amount_cents, timestamp):
    reference_id = f"appsul-hml-{payment_method.lower()}-{timestamp}-{secrets.token_hex(3)}"
    expires_at = (_now() + timedelta(hours=24)).isoformat()
    payment_methods = [{"type": payment_method}]
    configs = []

    if payment_method == "CREDIT_CARD":
        configs = [
            {
                "type": "CREDIT_CARD",
                "config_options": [
                    {"option": "INSTALLMENTS_LIMIT", "value": "12"}
                ],
            }
        ]

    return {
        "reference_id": reference_id,
        "customer": {
            "name": f"Homologacao PagBank {payment_method}",
            "email": f"homologacao+{reference_id}@appsul.com.br",
            "tax_id": "52998224725",
        },
        "customer_modifiable": True,
        "items": [
            {
                "reference_id": "pro-monthly",
                "name": "Profissional Mensal - Homologacao PagBank",
                "quantity": 1,
                "unit_amount": amount_cents,
            }
        ],
        "payment_methods": payment_methods,
        "payment_methods_configs": configs,
        "notification_urls": [f"{base_url}/webhooks/pagseguro"],
        "payment_notification_urls": [f"{base_url}/webhooks/pagseguro"],
        "redirect_url": f"{base_url}/checkout/{reference_id}/success",
        "return_url": f"{base_url}/checkout/{reference_id}/success",
        "expiration_date": expires_at,
        "soft_descriptor": (os.getenv("PAGBANK_SOFT_DESCRIPTOR") or "APPSUL").strip()[:17],
    }


def _call_checkout(api_base_url, token, platform_base_url, payment_method, amount_cents, timestamp, timeout):
    endpoint = f"{api_base_url}/checkouts"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = _checkout_payload(payment_method, platform_base_url, amount_cents, timestamp)

    started_at = _now().isoformat()
    try:
        response = requests.post(endpoint, json=payload, headers=headers, timeout=timeout)
        finished_at = _now().isoformat()
        try:
            response_body = response.json()
        except ValueError:
            response_body = {"raw_text": response.text}

        return {
            "payment_method": payment_method,
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
                "body": response_body,
            },
        }
    except Exception as exc:
        return {
            "payment_method": payment_method,
            "started_at": started_at,
            "finished_at": _now().isoformat(),
            "endpoint": endpoint,
            "http_method": "POST",
            "request": {
                "headers": _redact_headers(headers),
                "body": payload,
            },
            "response": {
                "status_code": None,
                "error": f"{type(exc).__name__}: {exc}",
            },
        }


def main():
    parser = argparse.ArgumentParser(description="Gera evidencia de request/response PagBank em sandbox.")
    parser.add_argument("--base-url", default=os.getenv("PLATFORM_BASE_URL", "https://app.appsul.com.br"))
    parser.add_argument("--output", default="/tmp/pagbank_sandbox_evidence.json")
    parser.add_argument("--amount-cents", type=int, default=34900)
    parser.add_argument("--timeout", type=int, default=25)
    args = parser.parse_args()

    api_base_url, token = _sandbox_config()
    platform_base_url = args.base_url.rstrip("/")
    timestamp = _now().strftime("%Y%m%d%H%M%S")

    evidence = {
        "title": "Evidencia de homologacao PagBank - Checkout Sandbox",
        "generated_at": _now().isoformat(),
        "environment": {
            "PAGBANK_ENVIRONMENT": os.getenv("PAGBANK_ENVIRONMENT"),
            "PAGBANK_API_BASE_URL": api_base_url,
            "PLATFORM_BASE_URL": platform_base_url,
        },
        "payment_methods_tested": ["CREDIT_CARD", "PIX"],
        "cases": [],
    }

    for payment_method in evidence["payment_methods_tested"]:
        evidence["cases"].append(
            _call_checkout(
                api_base_url=api_base_url,
                token=token,
                platform_base_url=platform_base_url,
                payment_method=payment_method,
                amount_cents=args.amount_cents,
                timestamp=timestamp,
                timeout=args.timeout,
            )
        )

    output_path = Path(args.output)
    _write_json(output_path, evidence)
    print(f"Evidencia gerada em: {output_path}")
    for case in evidence["cases"]:
        print(f"{case['payment_method']}: HTTP {case['response'].get('status_code')}")


if __name__ == "__main__":
    main()
