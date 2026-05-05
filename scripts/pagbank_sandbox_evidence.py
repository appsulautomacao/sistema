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


def _checkout_payload(platform_base_url, amount_cents):
    timestamp = _now().strftime("%Y%m%d%H%M%S")
    reference_id = f"appsul-hml-checkout-{timestamp}-{secrets.token_hex(3)}"
    expires_at = (_now() + timedelta(hours=24)).isoformat()

    return {
        "customer": {
            "name": "Homologacao PagBank Appsul",
            "email": f"homologacao+{reference_id}@appsul.com.br",
            "tax_id": "52998224725",
        },
        "reference_id": reference_id,
        "expiration_date": expires_at,
        "payment_methods": [
            {"type": "CREDIT_CARD"},
            {"type": "PIX"},
        ],
        "payment_methods_configs": [
            {
                "type": "CREDIT_CARD",
                "config_options": [
                    {"option": "INSTALLMENTS_LIMIT", "value": "12"}
                ],
            }
        ],
        "soft_descriptor": (os.getenv("PAGBANK_SOFT_DESCRIPTOR") or "APPSUL").strip()[:17],
        "redirect_url": f"{platform_base_url}/checkout/{reference_id}/success",
        "return_url": f"{platform_base_url}/checkout/{reference_id}/success",
        "notification_urls": [f"{platform_base_url}/webhooks/pagseguro"],
        "payment_notification_urls": [f"{platform_base_url}/webhooks/pagseguro"],
        "customer_modifiable": True,
        "items": [
            {
                "reference_id": "pro-monthly",
                "name": "Profissional Mensal - Homologacao PagBank",
                "quantity": 1,
                "unit_amount": amount_cents,
            }
        ],
    }


def _json_block(value):
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=False)


def _write_log(path, request_payload, response_payload):
    content = "\n\n".join(
        [
            "Request",
            _json_block(request_payload),
            "Response",
            _json_block(response_payload),
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Gera log de request/response real do Checkout PagBank Sandbox.")
    parser.add_argument("--base-url", default=os.getenv("PLATFORM_BASE_URL", "https://app.appsul.com.br"))
    parser.add_argument("--output", default="/tmp/pagbank_checkout_log.txt")
    parser.add_argument("--amount-cents", type=int, default=34900)
    parser.add_argument("--timeout", type=int, default=25)
    args = parser.parse_args()

    api_base_url, token = _sandbox_config()
    platform_base_url = args.base_url.rstrip("/")
    endpoint = f"{api_base_url}/checkouts"
    request_payload = _checkout_payload(platform_base_url, args.amount_cents)

    try:
        response = requests.post(
            endpoint,
            json=request_payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=args.timeout,
        )
        try:
            response_payload = response.json()
        except ValueError:
            response_payload = {"raw_text": response.text}
    except Exception as exc:
        response_payload = {"error": f"{type(exc).__name__}: {exc}"}

    output_path = Path(args.output)
    _write_log(output_path, request_payload, response_payload)
    print(f"Log gerado em: {output_path}")
    if isinstance(response_payload, dict):
        print(f"Checkout id: {response_payload.get('id') or '-'}")
        print(f"Status: {response_payload.get('status') or response_payload.get('error') or '-'}")


if __name__ == "__main__":
    main()
