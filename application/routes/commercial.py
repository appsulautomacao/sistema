import os

from flask import Blueprint, flash, redirect, render_template, request, url_for

from core.commercial_service import (
    create_checkout_session,
    format_brl,
    get_checkout_session_by_token,
    list_public_billing_plans,
    register_provider_checkout,
)
from core.whatsapp_authorization import normalize_whatsapp_number
from core.pagbank_service import create_pagbank_checkout, pagbank_is_configured


commercial_bp = Blueprint("commercial", __name__)


@commercial_bp.route("/planos")
def plans():
    plans_list = list_public_billing_plans()
    return render_template(
        "public/plans.html",
        plans=plans_list,
    )


@commercial_bp.route("/checkout/start", methods=["POST"])
def start_checkout():
    plan_code = (request.form.get("plan_code") or "").strip()
    company_name = (request.form.get("company_name") or "").strip()
    admin_name = (request.form.get("admin_name") or "Admin").strip() or "Admin"
    admin_email = (request.form.get("admin_email") or "").strip().lower()
    customer_document = (request.form.get("customer_document") or "").strip()
    whatsapp_number = (request.form.get("whatsapp_number") or "").strip()
    payment_method = (request.form.get("payment_method") or "card").strip().lower()
    installment_count = request.form.get("installment_count") or "1"
    coupon_code = (request.form.get("coupon_code") or "").strip()

    if not plan_code or not company_name or not admin_email:
        flash("Informe plano, empresa e e-mail do responsavel.", "warning")
        return redirect(url_for("commercial.plans"))

    normalized_whatsapp = normalize_whatsapp_number(whatsapp_number)
    if not normalized_whatsapp:
        flash("Informe um WhatsApp valido da empresa com DDD.", "warning")
        return redirect(url_for("commercial.plans"))

    try:
        session = create_checkout_session(
            plan_code=plan_code,
            company_name=company_name,
            admin_name=admin_name,
            admin_email=admin_email,
            customer_document=customer_document,
            payment_method=payment_method,
            installment_count=installment_count,
            coupon_code=coupon_code,
            success_url=url_for("commercial.checkout_success", public_token="__token__", _external=True),
            cancel_url=url_for("commercial.plans", _external=True),
        )
    except ValueError as exc:
        flash(str(exc), "warning")
        return redirect(url_for("commercial.plans"))

    session.success_url = url_for("commercial.checkout_success", public_token=session.public_token, _external=True)
    session.metadata_json = {
        **(session.metadata_json or {}),
        "success_url": session.success_url,
        "authorized_whatsapp_number": normalized_whatsapp,
        "authorized_whatsapp_source": "checkout" if normalized_whatsapp else None,
    }

    from db import db
    db.session.commit()

    return redirect(url_for("commercial.checkout_status", public_token=session.public_token))


@commercial_bp.route("/checkout/<public_token>")
def checkout_status(public_token):
    session = get_checkout_session_by_token(public_token)
    if not session:
        return "Checkout nao encontrado", 404
    if session.status == "paid":
        return redirect(url_for("commercial.checkout_success", public_token=session.public_token))

    metadata_json = session.metadata_json or {}
    checkout_payload = {
        "reference": session.public_token,
        "plan_code": session.plan.code,
        "payment_method": session.payment_method,
        "installments": session.installment_count,
        "amount_cents": session.amount_cents,
        "amount_display": session.amount_display,
        "coupon_code": metadata_json.get("coupon_code"),
        "coupon_trial_days": metadata_json.get("coupon_trial_days"),
    }

    return render_template(
        "public/checkout.html",
        session=session,
        plan=session.plan,
        checkout_payload=checkout_payload,
        pay_url=metadata_json.get("pay_url"),
        pagbank_configured=pagbank_is_configured(),
        format_brl=format_brl,
    )


@commercial_bp.route("/checkout/<public_token>/success")
def checkout_success(public_token):
    session = get_checkout_session_by_token(public_token)
    if not session:
        return "Checkout nao encontrado", 404

    training_url = (
        os.getenv("CUSTOMER_TRAINING_URL")
        or os.getenv("APPSUL_TRAINING_URL")
        or "https://appsul.com.br"
    ).strip()

    login_url = None
    if session.company and session.company.slug:
        platform_base_url = (os.getenv("PLATFORM_BASE_URL") or request.host_url).rstrip("/")
        login_url = f"{platform_base_url}/{session.company.slug}/login"

    return render_template(
        "public/checkout_success.html",
        session=session,
        plan=session.plan,
        training_url=training_url,
        login_url=login_url,
    )


@commercial_bp.route("/checkout/<public_token>/pay", methods=["POST"])
def redirect_to_provider_checkout(public_token):
    session = get_checkout_session_by_token(public_token)
    if not session:
        return "Checkout nao encontrado", 404

    metadata_json = session.metadata_json or {}
    if metadata_json.get("pay_url"):
        return redirect(metadata_json["pay_url"])

    platform_base_url = (os.getenv("PLATFORM_BASE_URL") or request.host_url).rstrip("/")
    is_public_base_url = platform_base_url.startswith("https://") and "localhost" not in platform_base_url and "127.0.0.1" not in platform_base_url
    webhook_url = f"{platform_base_url}/webhooks/pagseguro" if is_public_base_url else None
    return_url = url_for("commercial.checkout_success", public_token=session.public_token, _external=True) if is_public_base_url else None

    try:
        provider_checkout = create_pagbank_checkout(
            session=session,
            plan=session.plan,
            webhook_url=webhook_url,
            return_url=return_url,
        )
        register_provider_checkout(
            session=session,
            provider_checkout_id=provider_checkout["provider_checkout_id"],
            pay_url=provider_checkout["pay_url"],
            provider_response=provider_checkout["provider_response"],
        )
    except ValueError as exc:
        flash(str(exc), "warning")
        return redirect(url_for("commercial.checkout_status", public_token=session.public_token))

    return redirect(provider_checkout["pay_url"])
