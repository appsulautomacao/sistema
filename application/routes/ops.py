from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required
from sqlalchemy import func
from werkzeug.security import generate_password_hash

from core.billing_service import enqueue_pagseguro_payload, process_billing_event
from core.company_provisioning import generate_temporary_password, provision_company_with_admin
from core.super_admin import is_super_admin_user
from db import db
from models import (
    BillingEvent,
    CheckoutSession,
    Company,
    CompanySettings,
    Conversation,
    Message,
    MessageAttachment,
    PaymentTransaction,
    Subscription,
    User,
)


ops_bp = Blueprint("ops", __name__, url_prefix="/ops")


def _require_super_admin():
    if not is_super_admin_user(current_user):
        return "Acesso negado", 403
    return None


def _ensure_settings(company_id):
    settings = CompanySettings.query.filter_by(company_id=company_id).first()
    if not settings:
        settings = CompanySettings(company_id=company_id, plan="trial")
        db.session.add(settings)
        db.session.flush()
    return settings


@ops_bp.route("/")
@login_required
def index():
    denied = _require_super_admin()
    if denied:
        return denied
    return redirect(url_for("ops.clients"))


@ops_bp.route("/clients")
@login_required
def clients():
    denied = _require_super_admin()
    if denied:
        return denied

    companies = Company.query.order_by(Company.created_at.desc()).all()

    company_rows = []
    for company in companies:
        settings = _ensure_settings(company.id)
        users_count = User.query.filter_by(company_id=company.id).count()
        conversations_count = Conversation.query.filter_by(company_id=company.id).count()
        messages_count = Message.query.filter_by(company_id=company.id).count()
        subscriptions_count = Subscription.query.filter_by(company_id=company.id).count()
        latest_subscription = Subscription.query.filter_by(company_id=company.id).order_by(Subscription.created_at.desc()).first()
        paid_transactions_count = PaymentTransaction.query.filter_by(company_id=company.id, status="paid").count()
        attachments_bytes = db.session.query(
            func.coalesce(func.sum(MessageAttachment.size_bytes), 0)
        ).filter(
            MessageAttachment.company_id == company.id
        ).scalar() or 0

        company_rows.append({
            "company": company,
            "plan": settings.plan or "trial",
            "users_count": users_count,
            "conversations_count": conversations_count,
            "messages_count": messages_count,
            "subscriptions_count": subscriptions_count,
            "latest_subscription": latest_subscription,
            "paid_transactions_count": paid_transactions_count,
            "attachments_bytes": int(attachments_bytes),
        })

    latest_provision = session.pop("ops_latest_provision", None)

    return render_template(
        "ops/clients.html",
        company_rows=company_rows,
        latest_provision=latest_provision,
    )


@ops_bp.route("/simulator")
@login_required
def simulator():
    denied = _require_super_admin()
    if denied:
        return denied
    return render_template("ops/payment_simulator.html")


@ops_bp.route("/simulator/run", methods=["POST"])
@login_required
def run_simulator():
    denied = _require_super_admin()
    if denied:
        return denied

    company_name = (request.form.get("company_name") or "").strip()
    admin_name = (request.form.get("admin_name") or "Admin").strip() or "Admin"
    admin_email = (request.form.get("admin_email") or "").strip().lower()
    event_id = (request.form.get("event_id") or "").strip()

    if not company_name or not admin_email:
        flash("Informe nome da empresa e e-mail do admin.", "warning")
        return redirect(url_for("ops.simulator"))

    if not event_id:
        event_id = f"evt_sim_{company_name.lower().replace(' ', '_')}_{admin_email.split('@')[0]}"

    payload = {
        "id": event_id,
        "type": "payment.paid",
        "status": "PAID",
        "metadata": {
            "company_name": company_name,
            "admin_name": admin_name,
            "admin_email": admin_email,
        },
    }

    enqueue_response, enqueue_status = enqueue_pagseguro_payload(payload=payload)
    if enqueue_status == 200 and enqueue_response.get("status") == "duplicate_ignored":
        flash("Simulacao retornou: duplicate_ignored", "warning")
        return redirect(url_for("ops.simulator"))

    event_id_value = enqueue_response.get("event_id")
    response, status_code = process_billing_event(
        event_id=event_id_value,
        base_url=request.host_url,
        include_sensitive=True,
        force=False,
    )

    if status_code >= 500:
        flash(f"Simulacao falhou: {response.get('error', 'erro interno')}", "warning")
        return redirect(url_for("ops.simulator"))

    if response.get("status") == "provisioned":
        admin_email_value = response.get("admin_email") or admin_email
        session["ops_latest_provision"] = {
            "company_id": response["company_id"],
            "company_name": company_name,
            "slug": response["company_slug"],
            "admin_name": admin_name,
            "admin_email": admin_email_value,
            "temporary_password": response.get("temporary_password"),
            "login_url": response["login_url"],
            "email_result": None,
        }
        flash("Simulacao concluida: cliente provisionado com sucesso.", "success")
        return redirect(url_for("ops.clients"))

    flash(f"Simulacao retornou: {response.get('status')}", "warning")
    return redirect(url_for("ops.simulator"))


@ops_bp.route("/billing-events")
@login_required
def billing_events():
    denied = _require_super_admin()
    if denied:
        return denied

    events = BillingEvent.query.order_by(BillingEvent.created_at.desc()).limit(300).all()
    checkout_sessions_count = CheckoutSession.query.count()
    subscriptions_count = Subscription.query.count()
    paid_transactions_count = PaymentTransaction.query.filter_by(status="paid").count()
    summary = {
        "total": len(events),
        "processed": len([e for e in events if e.processed]),
        "pending": len([e for e in events if (not e.processed and not e.processing_error)]),
        "failed": len([e for e in events if (not e.processed and e.processing_error and e.processing_error != "__processing__")]),
        "checkout_sessions": checkout_sessions_count,
        "subscriptions": subscriptions_count,
        "paid_transactions": paid_transactions_count,
    }

    return render_template(
        "ops/billing_events.html",
        events=events,
        summary=summary,
    )


@ops_bp.route("/billing-events/<int:event_id>/reprocess", methods=["POST"])
@login_required
def reprocess_billing_event(event_id):
    denied = _require_super_admin()
    if denied:
        return denied

    response, status_code = process_billing_event(
        event_id=event_id,
        base_url=request.host_url,
        include_sensitive=True,
        force=True,
    )

    if status_code >= 500:
        flash(f"Falha no reprocessamento: {response.get('error', 'erro interno')}", "warning")
        return redirect(url_for("ops.billing_events"))

    if response.get("status") == "provisioned":
        company = Company.query.get(response["company_id"])
        admin_user = User.query.filter_by(company_id=response["company_id"], role="ADMIN").order_by(User.id.asc()).first()
        session["ops_latest_provision"] = {
            "company_id": response["company_id"],
            "company_name": company.name if company else "-",
            "slug": response["company_slug"],
            "admin_name": admin_user.name if admin_user else "Admin",
            "admin_email": response.get("admin_email") or (admin_user.email if admin_user else "-"),
            "temporary_password": response.get("temporary_password"),
            "login_url": response["login_url"],
            "email_result": None,
        }
        flash("Evento reprocessado com provisionamento concluido.", "success")
        return redirect(url_for("ops.clients"))

    flash(f"Reprocessamento retornou: {response.get('status')}", "warning")
    return redirect(url_for("ops.billing_events"))


@ops_bp.route("/clients/create", methods=["POST"])
@login_required
def create_client():
    denied = _require_super_admin()
    if denied:
        return denied

    company_name = (request.form.get("company_name") or "").strip()
    admin_name = (request.form.get("admin_name") or "Admin").strip() or "Admin"
    admin_email = (request.form.get("admin_email") or "").strip().lower()
    send_email = (request.form.get("send_email") == "on")

    if not company_name or not admin_email:
        flash("Informe nome da empresa e e-mail do admin.", "warning")
        return redirect(url_for("ops.clients"))

    base_url = request.host_url.rstrip("/")

    try:
        result = provision_company_with_admin(
            company_name=company_name,
            admin_name=admin_name,
            admin_email=admin_email,
            base_url=base_url,
            send_email=send_email,
        )
    except ValueError as exc:
        flash(str(exc), "warning")
        return redirect(url_for("ops.clients"))

    session["ops_latest_provision"] = result
    flash("Cliente criado com sucesso.", "success")
    return redirect(url_for("ops.clients"))


@ops_bp.route("/clients/<int:company_id>/block", methods=["POST"])
@login_required
def block_client(company_id):
    denied = _require_super_admin()
    if denied:
        return denied

    company = Company.query.get_or_404(company_id)
    settings = _ensure_settings(company.id)
    settings.plan = "blocked"
    db.session.commit()
    flash(f"Cliente {company.name} bloqueado.", "success")
    return redirect(url_for("ops.clients"))


@ops_bp.route("/clients/<int:company_id>/activate", methods=["POST"])
@login_required
def activate_client(company_id):
    denied = _require_super_admin()
    if denied:
        return denied

    company = Company.query.get_or_404(company_id)
    settings = _ensure_settings(company.id)
    settings.plan = "active"
    db.session.commit()
    flash(f"Cliente {company.name} ativado.", "success")
    return redirect(url_for("ops.clients"))


@ops_bp.route("/clients/<int:company_id>/reset-admin", methods=["POST"])
@login_required
def reset_admin_password(company_id):
    denied = _require_super_admin()
    if denied:
        return denied

    company = Company.query.get_or_404(company_id)
    admin_user = User.query.filter_by(company_id=company.id, role="ADMIN").order_by(User.id.asc()).first()
    if not admin_user:
        flash("Nao existe usuario ADMIN para este cliente.", "warning")
        return redirect(url_for("ops.clients"))

    temporary_password = generate_temporary_password()
    admin_user.password = generate_password_hash(temporary_password)
    admin_user.is_first_login = True
    db.session.commit()

    session["ops_latest_provision"] = {
        "company_id": company.id,
        "company_name": company.name,
        "slug": company.slug,
        "admin_name": admin_user.name,
        "admin_email": admin_user.email,
        "temporary_password": temporary_password,
        "login_url": f"{request.host_url.rstrip('/')}/{company.slug}/login",
        "email_result": None,
    }

    flash("Senha do admin resetada com sucesso.", "success")
    return redirect(url_for("ops.clients"))
