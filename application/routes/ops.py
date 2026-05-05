from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required
from sqlalchemy import func
from werkzeug.security import generate_password_hash

from core.billing_service import (
    enqueue_pagseguro_payload,
    process_billing_event,
    should_send_credentials_email,
)
from core.company_provisioning import (
    generate_temporary_password,
    provision_company_with_admin,
    send_credentials_email,
)
from core.super_admin import get_super_admin_emails, is_super_admin_user
from db import db
from models import (
    BillingEvent,
    CheckoutSession,
    AILog,
    Company,
    CompanySettings,
    ConversationHistory,
    ConversationRouting,
    Conversation,
    Message,
    MessageAttachment,
    Notification,
    PaymentTransaction,
    Sector,
    SLAEvent,
    Subscription,
    User,
    UserPresence,
    WhatsAppInstance,
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


def _format_brl(cents):
    value = (cents or 0) / 100
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _format_bytes(size_bytes):
    value = float(size_bytes or 0)
    for unit in ["B", "KB", "MB", "GB"]:
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024


def _is_protected_company(company):
    if (company.slug or "").strip().lower() == "appsul":
        return True

    super_admin_emails = get_super_admin_emails()
    if not super_admin_emails:
        return False

    return User.query.filter(
        User.company_id == company.id,
        func.lower(User.email).in_(sorted(super_admin_emails)),
    ).first() is not None


def _delete_company_data(company):
    conversation_ids = [
        item[0] for item in db.session.query(Conversation.id)
        .filter(Conversation.company_id == company.id)
        .all()
    ]
    user_ids = [
        item[0] for item in db.session.query(User.id)
        .filter(User.company_id == company.id)
        .all()
    ]
    checkout_session_ids = [
        item[0] for item in db.session.query(CheckoutSession.id)
        .filter(CheckoutSession.company_id == company.id)
        .all()
    ]
    subscription_ids = [
        item[0] for item in db.session.query(Subscription.id)
        .filter(Subscription.company_id == company.id)
        .all()
    ]
    billing_event_ids = {
        item[0] for item in db.session.query(BillingEvent.id)
        .filter(BillingEvent.company_id == company.id)
        .all()
    }
    if checkout_session_ids:
        billing_event_ids.update(
            item[0] for item in db.session.query(BillingEvent.id)
            .filter(BillingEvent.checkout_session_id.in_(checkout_session_ids))
            .all()
        )

    MessageAttachment.query.filter(MessageAttachment.company_id == company.id).delete(synchronize_session=False)
    if conversation_ids:
        MessageAttachment.query.filter(MessageAttachment.conversation_id.in_(conversation_ids)).delete(synchronize_session=False)
        Message.query.filter(Message.conversation_id.in_(conversation_ids)).delete(synchronize_session=False)
        SLAEvent.query.filter(SLAEvent.conversation_id.in_(conversation_ids)).delete(synchronize_session=False)
        Notification.query.filter(Notification.conversation_id.in_(conversation_ids)).delete(synchronize_session=False)
        ConversationHistory.query.filter(ConversationHistory.conversation_id.in_(conversation_ids)).delete(synchronize_session=False)
        ConversationRouting.query.filter(ConversationRouting.conversation_id.in_(conversation_ids)).delete(synchronize_session=False)

    Message.query.filter(Message.company_id == company.id).delete(synchronize_session=False)
    ConversationRouting.query.filter(ConversationRouting.company_id == company.id).delete(synchronize_session=False)
    ConversationHistory.query.filter(ConversationHistory.company_id == company.id).delete(synchronize_session=False)
    Conversation.query.filter(Conversation.company_id == company.id).delete(synchronize_session=False)

    UserPresence.query.filter(UserPresence.company_id == company.id).delete(synchronize_session=False)
    AILog.query.filter(AILog.company_id == company.id).delete(synchronize_session=False)
    WhatsAppInstance.query.filter(WhatsAppInstance.company_id == company.id).delete(synchronize_session=False)

    if billing_event_ids:
        PaymentTransaction.query.filter(PaymentTransaction.billing_event_id.in_(billing_event_ids)).delete(synchronize_session=False)
    if subscription_ids:
        PaymentTransaction.query.filter(PaymentTransaction.subscription_id.in_(subscription_ids)).delete(synchronize_session=False)
    if checkout_session_ids:
        PaymentTransaction.query.filter(PaymentTransaction.checkout_session_id.in_(checkout_session_ids)).delete(synchronize_session=False)

    PaymentTransaction.query.filter(PaymentTransaction.company_id == company.id).delete(synchronize_session=False)
    Subscription.query.filter(Subscription.company_id == company.id).delete(synchronize_session=False)
    if billing_event_ids:
        BillingEvent.query.filter(BillingEvent.id.in_(billing_event_ids)).delete(synchronize_session=False)
    CheckoutSession.query.filter(CheckoutSession.company_id == company.id).delete(synchronize_session=False)

    if user_ids:
        UserPresence.query.filter(UserPresence.user_id.in_(user_ids)).delete(synchronize_session=False)
    User.query.filter(User.company_id == company.id).delete(synchronize_session=False)
    Sector.query.filter(Sector.company_id == company.id).delete(synchronize_session=False)
    CompanySettings.query.filter(CompanySettings.company_id == company.id).delete(synchronize_session=False)
    db.session.delete(company)


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
        latest_transaction = PaymentTransaction.query.filter_by(company_id=company.id).order_by(PaymentTransaction.created_at.desc()).first()
        admin_user = User.query.filter_by(company_id=company.id, role="ADMIN").order_by(User.id.asc()).first()
        paid_transactions_count = PaymentTransaction.query.filter_by(company_id=company.id, status="paid").count()
        paid_amount_cents = db.session.query(
            func.coalesce(func.sum(PaymentTransaction.amount_cents), 0)
        ).filter(
            PaymentTransaction.company_id == company.id,
            PaymentTransaction.status == "paid",
        ).scalar() or 0
        ai_logs_count = AILog.query.filter_by(company_id=company.id).count()
        ai_fallback_count = AILog.query.filter_by(company_id=company.id, used_fallback=True).count()
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
            "latest_subscription_amount_display": _format_brl(latest_subscription.amount_cents) if latest_subscription else None,
            "latest_transaction": latest_transaction,
            "admin_user": admin_user,
            "paid_transactions_count": paid_transactions_count,
            "paid_amount_display": _format_brl(int(paid_amount_cents)),
            "ai_logs_count": ai_logs_count,
            "ai_fallback_count": ai_fallback_count,
            "attachments_bytes": int(attachments_bytes),
            "attachments_display": _format_bytes(attachments_bytes),
            "is_protected": _is_protected_company(company),
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
            "email_result": response.get("email_result"),
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
            "email_result": response.get("email_result"),
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


@ops_bp.route("/clients/<int:company_id>/delete", methods=["POST"])
@login_required
def delete_client(company_id):
    denied = _require_super_admin()
    if denied:
        return denied

    company = Company.query.get_or_404(company_id)
    if _is_protected_company(company):
        flash("Este cliente esta protegido e nao pode ser excluido pelo Ops.", "warning")
        return redirect(url_for("ops.clients"))

    company_name = company.name
    _delete_company_data(company)
    db.session.commit()
    flash(f"Cliente {company_name} excluido com sucesso.", "success")
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
    login_url = f"{request.host_url.rstrip('/')}/{company.slug}/login"
    email_result = None
    if should_send_credentials_email():
        sent, detail = send_credentials_email(
            admin_email=admin_user.email,
            admin_name=admin_user.name,
            company_name=company.name,
            login_url=login_url,
            password=temporary_password,
        )
        email_result = {"sent": sent, "detail": detail}
    db.session.commit()

    session["ops_latest_provision"] = {
        "company_id": company.id,
        "company_name": company.name,
        "slug": company.slug,
        "admin_name": admin_user.name,
        "admin_email": admin_user.email,
        "temporary_password": temporary_password,
        "login_url": login_url,
        "email_result": email_result,
    }

    if email_result and not email_result["sent"]:
        flash(f"Senha resetada, mas o e-mail falhou: {email_result['detail']}", "warning")
    else:
        flash("Senha do admin resetada com sucesso.", "success")
    return redirect(url_for("ops.clients"))
