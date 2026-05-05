from datetime import datetime, timedelta
import os
import secrets

from db import db
from models import (
    BillingPlan,
    CheckoutSession,
    CompanySettings,
    PaymentTransaction,
    Subscription,
    User,
)


def format_brl(cents):
    value = (cents or 0) / 100
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _configured_test_coupon():
    code = (os.getenv("COMMERCIAL_TEST_COUPON_CODE") or "TESTE3DIAS").strip().upper()
    if not code:
        return None

    try:
        price_cents = int(os.getenv("COMMERCIAL_TEST_COUPON_PRICE_CENTS", "500"))
    except ValueError:
        price_cents = 500

    try:
        trial_days = int(os.getenv("COMMERCIAL_TEST_COUPON_DAYS", "3"))
    except ValueError:
        trial_days = 3

    trial_days = max(trial_days, 1)
    return {
        "code": code,
        "final_amount_cents": max(price_cents, 100),
        "trial_days": trial_days,
        "description": f"Teste de {trial_days} dias",
    }


def apply_checkout_coupon(coupon_code, original_amount_cents):
    normalized_code = (coupon_code or "").strip().upper()
    if not normalized_code:
        return None

    coupon = _configured_test_coupon()
    if not coupon or normalized_code != coupon["code"]:
        raise ValueError("Cupom invalido ou expirado.")

    final_amount_cents = min(original_amount_cents, coupon["final_amount_cents"])
    discount_cents = max(original_amount_cents - final_amount_cents, 0)
    return {
        **coupon,
        "discount_cents": discount_cents,
        "original_amount_cents": original_amount_cents,
        "final_amount_cents": final_amount_cents,
    }


DEFAULT_BILLING_PLANS = [
    {
        "code": "starter-monthly",
        "name": "Essencial Mensal",
        "description": "Para pequenas empresas que querem sair da bagunca do WhatsApp e comecar com atendimento organizado.",
        "billing_period": "monthly",
        "billing_cycle_months": 1,
        "price_cents": 19900,
        "max_installments": 12,
        "highlight_text": None,
        "sort_order": 10,
        "metadata_json": {"users_label": "ate 2 atendentes", "channel": "whatsapp"},
    },
    {
        "code": "pro-monthly",
        "name": "Profissional Mensal",
        "description": "Ideal para empresas que atendem todos os dias, tem equipe e precisam controlar conversas, setores e tempo de resposta.",
        "billing_period": "monthly",
        "billing_cycle_months": 1,
        "price_cents": 34900,
        "max_installments": 12,
        "highlight_text": "Mais vendido",
        "sort_order": 20,
        "metadata_json": {"users_label": "ate 5 atendentes", "channel": "whatsapp"},
    },
    {
        "code": "pro-yearly",
        "name": "Profissional Anual",
        "description": "Para empresas que querem reduzir custo, garantir a operacao anual e receber implantacao assistida com melhores condicoes.",
        "billing_period": "yearly",
        "billing_cycle_months": 12,
        "price_cents": 349000,
        "max_installments": 12,
        "highlight_text": "Economia anual",
        "sort_order": 30,
        "metadata_json": {"users_label": "ate 5 atendentes", "channel": "whatsapp"},
    },
    {
        "code": "implantacao-avista",
        "name": "Implantacao Assistida",
        "description": "Configuracao inicial da central, conexao do WhatsApp, criacao dos setores e orientacao para sua equipe comecar do jeito certo.",
        "billing_period": "one_time",
        "billing_cycle_months": 0,
        "price_cents": 99000,
        "max_installments": 12,
        "allow_boleto": False,
        "highlight_text": None,
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
            plan = BillingPlan.query.filter_by(code=raw_plan["code"]).first()
            changed = False
            for field in (
                "name",
                "description",
                "billing_period",
                "billing_cycle_months",
                "price_cents",
                "allow_pix",
                "allow_boleto",
                "allow_card",
                "max_installments",
                "highlight_text",
                "sort_order",
                "metadata_json",
            ):
                if getattr(plan, field) != raw_plan.get(field):
                    setattr(plan, field, raw_plan.get(field))
                    changed = True
            if changed:
                created = True
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
    metadata = session.metadata_json or {}
    return {
        "checkout_session_token": session.public_token,
        "plan_code": selected_plan.code,
        "billing_period": selected_plan.billing_period,
        "payment_method": session.payment_method,
        "installment_count": session.installment_count,
        "company_name": session.company_name,
        "admin_name": session.admin_name,
        "admin_email": session.admin_email,
        **metadata,
    }


def create_checkout_session(
    plan_code,
    company_name,
    admin_name,
    admin_email,
    customer_document=None,
    payment_method="card",
    installment_count=1,
    coupon_code=None,
    provider="pagseguro",
    success_url=None,
    cancel_url=None,
):
    normalized_admin_email = (admin_email or "").strip().lower()
    if not normalized_admin_email:
        raise ValueError("E-mail do responsavel e obrigatorio.")

    existing_user = User.query.filter_by(email=normalized_admin_email).first()
    if existing_user:
        raise ValueError("Este e-mail ja esta cadastrado. Use outro e-mail ou recupere o acesso existente.")

    existing_checkout = CheckoutSession.query.filter(
        CheckoutSession.admin_email == normalized_admin_email,
        CheckoutSession.status.in_(["created", "provider_created", "paid"]),
        CheckoutSession.expires_at > datetime.utcnow(),
    ).order_by(CheckoutSession.created_at.desc()).first()
    if existing_checkout:
        raise ValueError("Ja existe uma compra iniciada com este e-mail. Use outro e-mail ou fale com o suporte.")

    plan = get_billing_plan_by_code(plan_code)
    if not plan:
        raise ValueError("Plano nao encontrado.")

    method = (payment_method or "card").strip().lower()
    if method not in {"card", "pix"}:
        raise ValueError("Metodo de pagamento invalido.")

    if method == "card" and not plan.allow_card:
        raise ValueError("Este plano nao aceita cartao.")
    if method == "pix" and not plan.allow_pix:
        raise ValueError("Este plano nao aceita pix.")

    installments = int(installment_count or 1)
    installments = max(1, installments)
    if method != "card":
        installments = 1
    if installments > plan.max_installments:
        raise ValueError("Parcelamento acima do permitido para este plano.")

    original_amount_cents = plan.price_cents + (plan.setup_fee_cents or 0)
    coupon = apply_checkout_coupon(coupon_code, original_amount_cents) if coupon_code else None
    final_amount_cents = coupon["final_amount_cents"] if coupon else original_amount_cents
    metadata_json = {
        "original_amount_cents": original_amount_cents,
        "final_amount_cents": final_amount_cents,
    }
    if coupon:
        metadata_json.update({
            "coupon_code": coupon["code"],
            "coupon_description": coupon["description"],
            "coupon_discount_cents": coupon["discount_cents"],
            "coupon_trial_days": coupon["trial_days"],
        })

    session = CheckoutSession(
        public_token=secrets.token_urlsafe(24),
        plan_id=plan.id,
        company_name=(company_name or "").strip(),
        admin_name=(admin_name or "Admin").strip() or "Admin",
        admin_email=normalized_admin_email,
        customer_document=(customer_document or "").strip() or None,
        payment_method=method,
        installment_count=installments,
        amount_cents=final_amount_cents,
        currency=plan.currency,
        status="created",
        provider=provider,
        success_url=success_url,
        cancel_url=cancel_url,
        metadata_json=metadata_json,
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


def _checkout_trial_days(checkout_session):
    if not checkout_session or not checkout_session.metadata_json:
        return None
    try:
        trial_days = int(checkout_session.metadata_json.get("coupon_trial_days") or 0)
    except (TypeError, ValueError):
        return None
    return trial_days if trial_days > 0 else None


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
    trial_days = _checkout_trial_days(checkout_session)
    if trial_days:
        period_end = started_at + timedelta(days=trial_days)

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
            "coupon_code": (checkout_session.metadata_json or {}).get("coupon_code") if checkout_session else None,
            "trial_days": trial_days,
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
                "coupon_code": (checkout_session.metadata_json or {}).get("coupon_code") if checkout_session else None,
                "trial_days": trial_days,
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
