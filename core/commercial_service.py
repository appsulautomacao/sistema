from datetime import datetime, timedelta
import secrets

from db import db
from models import (
    BillingPlan,
    CheckoutSession,
    CompanySettings,
    PaymentTransaction,
    Subscription,
)


DEFAULT_BILLING_PLANS = [
    {
        "code": "starter-monthly",
        "name": "Starter Mensal",
        "description": "Entrada rapida para operar com atendimento e onboarding simples.",
        "billing_period": "monthly",
        "billing_cycle_months": 1,
        "price_cents": 19900,
        "max_installments": 12,
        "highlight_text": "Comeco rapido",
        "sort_order": 10,
        "metadata_json": {"users_label": "ate 3 usuarios", "channel": "whatsapp"},
    },
    {
        "code": "pro-monthly",
        "name": "Pro Mensal",
        "description": "Plano principal para operar todos os dias com equipe e IA.",
        "billing_period": "monthly",
        "billing_cycle_months": 1,
        "price_cents": 34900,
        "max_installments": 12,
        "highlight_text": "Mais vendido",
        "sort_order": 20,
        "metadata_json": {"users_label": "ate 10 usuarios", "channel": "whatsapp"},
    },
    {
        "code": "pro-yearly",
        "name": "Pro Anual",
        "description": "Pagamento anual com economia e ativacao imediata.",
        "billing_period": "yearly",
        "billing_cycle_months": 12,
        "price_cents": 349000,
        "max_installments": 12,
        "highlight_text": "Melhor custo anual",
        "sort_order": 30,
        "metadata_json": {"users_label": "ate 10 usuarios", "channel": "whatsapp"},
    },
    {
        "code": "implantacao-avista",
        "name": "Implantacao a Vista",
        "description": "Pagamento unico para setup inicial ou fee comercial.",
        "billing_period": "one_time",
        "billing_cycle_months": 0,
        "price_cents": 99000,
        "max_installments": 1,
        "allow_boleto": True,
        "highlight_text": "Pagamento unico",
        "sort_order": 40,
        "metadata_json": {"users_label": "setup comercial"},
    },
]


def ensure_default_billing_plans():
    existing_codes = {
        row[0]
        for row in db.session.query(BillingPlan.code).all()
    }
    created = False

    for raw_plan in DEFAULT_BILLING_PLANS:
        if raw_plan["code"] in existing_codes:
            continue
        db.session.add(BillingPlan(**raw_plan))
        created = True

    if created:
        db.session.commit()


def list_public_billing_plans():
    ensure_default_billing_plans()
    return BillingPlan.query.filter_by(
        is_public=True,
        is_active=True,
    ).order_by(BillingPlan.sort_order.asc(), BillingPlan.price_cents.asc()).all()


def get_billing_plan_by_code(plan_code):
    ensure_default_billing_plans()
    return BillingPlan.query.filter_by(code=plan_code, is_active=True).first()


def build_checkout_metadata(session, plan=None):
    selected_plan = plan or session.plan
    return {
        "checkout_session_token": session.public_token,
        "plan_code": selected_plan.code,
        "billing_period": selected_plan.billing_period,
        "payment_method": session.payment_method,
        "installment_count": session.installment_count,
        "company_name": session.company_name,
        "admin_name": session.admin_name,
        "admin_email": session.admin_email,
    }


def create_checkout_session(
    plan_code,
    company_name,
    admin_name,
    admin_email,
    customer_document=None,
    payment_method="card",
    installment_count=1,
    provider="pagseguro",
    success_url=None,
    cancel_url=None,
):
    plan = get_billing_plan_by_code(plan_code)
    if not plan:
        raise ValueError("Plano nao encontrado.")

    method = (payment_method or "card").strip().lower()
    if method not in {"card", "pix", "boleto"}:
        raise ValueError("Metodo de pagamento invalido.")

    if method == "card" and not plan.allow_card:
        raise ValueError("Este plano nao aceita cartao.")
    if method == "pix" and not plan.allow_pix:
        raise ValueError("Este plano nao aceita pix.")
    if method == "boleto" and not plan.allow_boleto:
        raise ValueError("Este plano nao aceita boleto.")

    installments = int(installment_count or 1)
    installments = max(1, installments)
    if method != "card":
        installments = 1
    if installments > plan.max_installments:
        raise ValueError("Parcelamento acima do permitido para este plano.")

    session = CheckoutSession(
        public_token=secrets.token_urlsafe(24),
        plan_id=plan.id,
        company_name=(company_name or "").strip(),
        admin_name=(admin_name or "Admin").strip() or "Admin",
        admin_email=(admin_email or "").strip().lower(),
        customer_document=(customer_document or "").strip() or None,
        payment_method=method,
        installment_count=installments,
        amount_cents=plan.price_cents + (plan.setup_fee_cents or 0),
        currency=plan.currency,
        status="created",
        provider=provider,
        success_url=success_url,
        cancel_url=cancel_url,
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )
    session.metadata_json = build_checkout_metadata(session, plan=plan)

    db.session.add(session)
    db.session.commit()
    return session


def get_checkout_session_by_token(public_token):
    return CheckoutSession.query.filter_by(public_token=public_token).first()


def register_provider_checkout(session, provider_checkout_id, pay_url, provider_response):
    session.external_checkout_id = provider_checkout_id
    session.status = "provider_created"
    session.metadata_json = {
        **(session.metadata_json or {}),
        "provider_checkout_id": provider_checkout_id,
        "pay_url": pay_url,
        "provider_response": provider_response,
    }
    db.session.commit()
    return session


def _ensure_company_settings(company_id):
    settings = CompanySettings.query.filter_by(company_id=company_id).first()
    if not settings:
        settings = CompanySettings(company_id=company_id)
        db.session.add(settings)
        db.session.flush()
    return settings


def _calculate_period_end(started_at, billing_cycle_months, billing_period):
    if billing_period == "one_time":
        return started_at
    months = billing_cycle_months or (12 if billing_period == "yearly" else 1)
    return started_at + timedelta(days=30 * months)


def activate_company_subscription(
    company_id,
    billing_event,
    plan=None,
    checkout_session=None,
    external_payment_id=None,
    payment_method=None,
    installment_count=None,
    amount_cents=None,
    payload_json=None,
):
    selected_plan = plan
    if not selected_plan and checkout_session:
        selected_plan = checkout_session.plan
    if not selected_plan and billing_event and billing_event.plan_code:
        selected_plan = get_billing_plan_by_code(billing_event.plan_code)
    if not selected_plan:
        selected_plan = get_billing_plan_by_code("starter-monthly")

    started_at = datetime.utcnow()
    period_end = _calculate_period_end(
        started_at=started_at,
        billing_cycle_months=selected_plan.billing_cycle_months,
        billing_period=selected_plan.billing_period,
    )

    active_subscription = Subscription.query.filter(
        Subscription.company_id == company_id,
        Subscription.status.in_(["active", "trial", "past_due"]),
    ).order_by(Subscription.created_at.desc()).first()

    if active_subscription:
        subscription = active_subscription
        subscription.plan_id = selected_plan.id
        subscription.status = "active"
        subscription.billing_period = selected_plan.billing_period
        subscription.amount_cents = amount_cents or selected_plan.price_cents
        subscription.currency = selected_plan.currency
        subscription.started_at = subscription.started_at or started_at
        subscription.current_period_start = started_at
        subscription.current_period_end = period_end
        subscription.checkout_session_id = checkout_session.id if checkout_session else subscription.checkout_session_id
        subscription.metadata_json = {
            "source": "billing_webhook",
            "plan_code": selected_plan.code,
        }
    else:
        subscription = Subscription(
            company_id=company_id,
            plan_id=selected_plan.id,
            checkout_session_id=checkout_session.id if checkout_session else None,
            provider=(billing_event.provider if billing_event else "pagseguro"),
            status="active",
            billing_period=selected_plan.billing_period,
            amount_cents=amount_cents or selected_plan.price_cents,
            currency=selected_plan.currency,
            started_at=started_at,
            current_period_start=started_at,
            current_period_end=period_end,
            metadata_json={
                "source": "billing_webhook",
                "plan_code": selected_plan.code,
            },
        )
        db.session.add(subscription)
        db.session.flush()

    transaction = PaymentTransaction(
        company_id=company_id,
        subscription_id=subscription.id,
        checkout_session_id=checkout_session.id if checkout_session else None,
        billing_event_id=billing_event.id if billing_event else None,
        provider=(billing_event.provider if billing_event else "pagseguro"),
        external_payment_id=external_payment_id,
        payment_method=payment_method or (checkout_session.payment_method if checkout_session else None),
        installment_count=installment_count or (checkout_session.installment_count if checkout_session else None),
        amount_cents=amount_cents or selected_plan.price_cents,
        currency=selected_plan.currency,
        status="paid",
        paid_at=started_at,
        payload_json=payload_json,
    )
    db.session.add(transaction)

    if checkout_session:
        checkout_session.company_id = company_id
        checkout_session.status = "paid"
        checkout_session.paid_at = started_at

    settings = _ensure_company_settings(company_id)
    settings.plan = "active"

    if billing_event:
        billing_event.company_id = company_id
        billing_event.checkout_session_id = checkout_session.id if checkout_session else billing_event.checkout_session_id
        billing_event.plan_code = selected_plan.code
        billing_event.billing_period = selected_plan.billing_period
        billing_event.payment_method = payment_method or billing_event.payment_method
        billing_event.installment_count = installment_count or billing_event.installment_count
        billing_event.amount_cents = amount_cents or billing_event.amount_cents or selected_plan.price_cents

    db.session.commit()

    return {
        "subscription_id": subscription.id,
        "plan_code": selected_plan.code,
        "payment_transaction_id": transaction.id,
        "current_period_end": period_end,
    }
