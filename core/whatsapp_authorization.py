from db import db
from models import CheckoutSession, Subscription


def normalize_whatsapp_number(value):
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if not digits:
        return None

    if digits.startswith("00"):
        digits = digits[2:]

    if len(digits) in {10, 11}:
        digits = f"55{digits}"

    return digits if 12 <= len(digits) <= 14 else None


def _metadata_number(metadata):
    if not metadata:
        return None
    return normalize_whatsapp_number(
        metadata.get("authorized_whatsapp_number")
        or metadata.get("registered_whatsapp_number")
        or metadata.get("whatsapp_number")
    )


def get_authorized_whatsapp_number(company_id):
    subscription = Subscription.query.filter_by(company_id=company_id).order_by(
        Subscription.created_at.desc()
    ).first()
    number = _metadata_number(subscription.metadata_json if subscription else None)
    if number:
        return number

    if subscription and subscription.checkout_session:
        number = _metadata_number(subscription.checkout_session.metadata_json)
        if number:
            return number

    checkout = CheckoutSession.query.filter_by(company_id=company_id).order_by(
        CheckoutSession.created_at.desc()
    ).first()
    return _metadata_number(checkout.metadata_json if checkout else None)


def set_authorized_whatsapp_number(company_id, number):
    normalized = normalize_whatsapp_number(number)
    if not normalized:
        raise ValueError("Informe um numero de WhatsApp valido com DDD.")

    subscription = Subscription.query.filter_by(company_id=company_id).order_by(
        Subscription.created_at.desc()
    ).first()
    if subscription:
        subscription.metadata_json = {
            **(subscription.metadata_json or {}),
            "authorized_whatsapp_number": normalized,
            "authorized_whatsapp_source": "client_panel",
        }
        if subscription.checkout_session:
            subscription.checkout_session.metadata_json = {
                **(subscription.checkout_session.metadata_json or {}),
                "authorized_whatsapp_number": normalized,
            }
    else:
        checkout = CheckoutSession.query.filter_by(company_id=company_id).order_by(
            CheckoutSession.created_at.desc()
        ).first()
        if not checkout:
            raise ValueError("Nao encontramos uma assinatura para salvar este WhatsApp.")
        checkout.metadata_json = {
            **(checkout.metadata_json or {}),
            "authorized_whatsapp_number": normalized,
            "authorized_whatsapp_source": "client_panel",
        }

    db.session.commit()
    return normalized


def numbers_match(left, right):
    left_normalized = normalize_whatsapp_number(left)
    right_normalized = normalize_whatsapp_number(right)
    return bool(left_normalized and right_normalized and left_normalized == right_normalized)
