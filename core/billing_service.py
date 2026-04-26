from datetime import datetime

from core.billing import (
    build_billing_dedupe_key,
    is_payment_approved,
    normalize_pagseguro_payload,
)
from core.commercial_service import (
    activate_company_subscription,
    get_billing_plan_by_code,
    get_checkout_session_by_token,
)
from core.company_provisioning import provision_company_with_admin
from db import db
from models import BillingEvent, Company, User


PROCESSING_SENTINEL = "__processing__"


def enqueue_pagseguro_payload(payload):
    payload = payload or {}
    data = normalize_pagseguro_payload(payload)

    dedupe_key = build_billing_dedupe_key(
        provider="pagseguro",
        external_event_id=data["external_event_id"],
        payload=payload,
    )

    existing = BillingEvent.query.filter_by(dedupe_key=dedupe_key).first()
    if existing:
        return {"status": "duplicate_ignored", "event_id": existing.id}, 200

    event = BillingEvent(
        provider="pagseguro",
        dedupe_key=dedupe_key,
        external_event_id=data["external_event_id"],
        event_type=data["event_type"],
        payment_status=data["payment_status"],
        reference=data["reference"],
        plan_code=data["plan_code"],
        billing_period=data["billing_period"],
        payment_method=data["payment_method"],
        installment_count=data["installment_count"],
        amount_cents=data["amount_cents"],
        company_name=data["company_name"],
        admin_name=data["admin_name"],
        admin_email=data["admin_email"],
        payload_json=payload,
        processed=False,
        processing_error=None,
    )
    db.session.add(event)
    db.session.commit()
    return {"status": "queued", "event_id": event.id}, 202


def _mark_event_processing(event):
    event.processing_error = PROCESSING_SENTINEL
    db.session.commit()


def process_billing_event(event_id, base_url, include_sensitive=False, force=False):
    event = BillingEvent.query.get(event_id)
    if not event:
        return {"status": "not_found"}, 404

    if event.processed and not force:
        return {"status": "already_processed", "event_id": event.id}, 200

    if event.processing_error == PROCESSING_SENTINEL and not force:
        return {"status": "already_processing", "event_id": event.id}, 200

    _mark_event_processing(event)

    data = normalize_pagseguro_payload(event.payload_json or {})
    checkout_session = None
    checkout_lookup_token = data["checkout_session_token"] or data["reference"]
    if checkout_lookup_token:
        checkout_session = get_checkout_session_by_token(checkout_lookup_token)
        if checkout_session:
            event.checkout_session_id = checkout_session.id
            event.plan_code = event.plan_code or checkout_session.plan.code
            event.company_name = event.company_name or checkout_session.company_name
            event.admin_name = event.admin_name or checkout_session.admin_name
            event.admin_email = event.admin_email or checkout_session.admin_email
            data["company_name"] = data["company_name"] or checkout_session.company_name
            data["admin_name"] = data["admin_name"] or checkout_session.admin_name
            data["admin_email"] = data["admin_email"] or checkout_session.admin_email
            data["payment_method"] = data["payment_method"] or checkout_session.payment_method
            data["installment_count"] = data["installment_count"] or checkout_session.installment_count

    if not is_payment_approved(data["payment_status"]):
        event.processed = True
        event.processing_error = f"status_not_approved:{data['payment_status']}"
        event.processed_at = datetime.utcnow()
        db.session.commit()
        return {"status": "ignored_payment_not_approved", "event_id": event.id}, 200

    if not data["company_name"] or not data["admin_email"]:
        event.processed = False
        event.processing_error = "missing_company_name_or_admin_email"
        db.session.commit()
        return {"status": "pending_manual_data", "event_id": event.id}, 200

    existing_user = User.query.filter_by(email=data["admin_email"]).first()
    if existing_user:
        event.company_id = existing_user.company_id
        event.processed = True
        event.processing_error = "admin_email_already_exists"
        event.processed_at = datetime.utcnow()
        db.session.commit()
        return {"status": "ignored_admin_exists", "event_id": event.id}, 200

    existing_company = Company.query.filter_by(name=data["company_name"]).first()
    if existing_company:
        event.company_id = existing_company.id
        event.processed = True
        event.processing_error = "company_name_already_exists"
        event.processed_at = datetime.utcnow()
        db.session.commit()
        return {"status": "ignored_company_exists", "event_id": event.id}, 200

    try:
        result = provision_company_with_admin(
            company_name=data["company_name"],
            admin_name=data["admin_name"] or "Admin",
            admin_email=data["admin_email"],
            base_url=base_url.rstrip("/"),
            send_email=False,
        )
    except Exception as exc:
        event.processed = False
        event.processing_error = str(exc)
        db.session.commit()
        return {"status": "failed", "error": str(exc), "event_id": event.id}, 500

    event.company_id = result["company_id"]
    event.processed = True
    event.processing_error = None
    event.processed_at = datetime.utcnow()
    db.session.commit()

    selected_plan = None
    if data["plan_code"]:
        selected_plan = get_billing_plan_by_code(data["plan_code"])
    if not selected_plan and checkout_session:
        selected_plan = checkout_session.plan

    subscription_result = activate_company_subscription(
        company_id=result["company_id"],
        billing_event=event,
        plan=selected_plan,
        checkout_session=checkout_session,
        external_payment_id=data["external_event_id"],
        payment_method=data["payment_method"],
        installment_count=data["installment_count"],
        amount_cents=data["amount_cents"],
        payload_json=event.payload_json,
    )

    response = {
        "status": "provisioned",
        "event_id": event.id,
        "company_id": result["company_id"],
        "company_slug": result["slug"],
        "login_url": result["login_url"],
        "admin_email": result["admin_email"],
        "plan_code": subscription_result["plan_code"],
        "subscription_id": subscription_result["subscription_id"],
    }
    if include_sensitive:
        response["temporary_password"] = result["temporary_password"]

    return response, 200


def process_pending_billing_events(base_url, max_events=20):
    events = BillingEvent.query.filter(
        BillingEvent.processed.is_(False),
        BillingEvent.processing_error.is_(None),
    ).order_by(BillingEvent.created_at.asc()).limit(max_events).all()

    results = []
    for event in events:
        response, status_code = process_billing_event(
            event_id=event.id,
            base_url=base_url,
            include_sensitive=False,
            force=False,
        )
        results.append(
            {
                "event_id": event.id,
                "status_code": status_code,
                "status": response.get("status"),
            }
        )
    return results
