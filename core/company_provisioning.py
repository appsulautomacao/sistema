import os
import secrets
import smtplib
from email.message import EmailMessage

from werkzeug.security import generate_password_hash

from core.company_identity import generate_unique_company_slug
from db import db
from models import Company, CompanySettings, Sector, User


def generate_temporary_password(length=14):
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%?"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def get_customer_training_url():
    return (
        os.getenv("CUSTOMER_TRAINING_URL")
        or os.getenv("APPSUL_TRAINING_URL")
        or "https://appsul.com.br"
    ).strip()


def send_credentials_email(admin_email, admin_name, company_name, login_url, password):
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_from = os.getenv("SMTP_FROM")
    smtp_use_tls = os.getenv("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes", "on"}
    training_url = get_customer_training_url()

    if not smtp_host or not smtp_from:
        return False, "SMTP nao configurado (defina SMTP_HOST e SMTP_FROM)."

    message = EmailMessage()
    message["Subject"] = f"Acesso administrativo - {company_name}"
    message["From"] = smtp_from
    message["To"] = admin_email
    message.set_content(
        f"""Ola {admin_name},

Seja bem-vindo(a) a plataforma de atendimento da App Sul.

Seu acesso administrativo foi criado e ja esta pronto para o primeiro login.

Empresa: {company_name}
Usuario: {admin_email}
Senha temporaria: {password}
Link de acesso: {login_url}

Primeiros passos:
1. Acesse o link acima usando seu e-mail e a senha temporaria.
2. No primeiro acesso, crie uma nova senha.
3. Finalize o onboarding da empresa.
4. Conecte o WhatsApp pelo painel.
5. Cadastre usuarios e setores para organizar o atendimento.

Treinamento e orientacoes:
{training_url}

Se tiver qualquer dificuldade, responda este e-mail ou fale com a equipe App Sul.
"""
    )

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
            if smtp_use_tls:
                server.starttls()

            if smtp_username and smtp_password:
                server.login(smtp_username, smtp_password)

            server.send_message(message)
    except Exception as exc:
        return False, f"Falha ao enviar e-mail: {exc}"

    return True, "E-mail enviado com sucesso."


def ensure_company_settings(company_id):
    settings = CompanySettings.query.filter_by(company_id=company_id).first()
    if not settings:
        settings = CompanySettings(company_id=company_id)
        db.session.add(settings)
        db.session.flush()
    return settings


def ensure_central_sector(company_id):
    settings = ensure_company_settings(company_id)

    central_sector = Sector.query.filter_by(
        company_id=company_id,
        is_central=True,
    ).order_by(Sector.id.asc()).first()

    if not central_sector:
        central_sector = Sector(
            name="Central",
            company_id=company_id,
            is_central=True,
        )
        db.session.add(central_sector)
        db.session.flush()

    if settings.central_sector_id != central_sector.id:
        settings.central_sector_id = central_sector.id

    return central_sector


def ensure_company_access_ready(company):
    if not company.slug:
        company.slug = generate_unique_company_slug(company.name, exclude_company_id=company.id)

    ensure_company_settings(company.id)
    ensure_central_sector(company.id)
    db.session.commit()


def provision_company_with_admin(company_name, admin_name, admin_email, base_url, send_email=False):
    normalized_email = (admin_email or "").strip().lower()
    if not normalized_email:
        raise ValueError("E-mail do admin e obrigatorio.")

    existing_admin = User.query.filter_by(email=normalized_email).first()
    if existing_admin:
        raise ValueError("Ja existe um usuario com esse e-mail.")

    company = Company(
        name=(company_name or "").strip(),
        slug=generate_unique_company_slug(company_name),
        onboarding_completed=False,
        primary_color="#0D6EFD",
    )
    db.session.add(company)
    db.session.flush()

    settings = ensure_company_settings(company.id)
    settings.plan = "active"
    ensure_central_sector(company.id)

    temporary_password = generate_temporary_password()
    admin = User(
        name=(admin_name or "Admin").strip() or "Admin",
        email=normalized_email,
        password=generate_password_hash(temporary_password),
        role="ADMIN",
        company_id=company.id,
        is_first_login=True,
    )
    db.session.add(admin)
    db.session.commit()

    login_url = f"{base_url.rstrip('/')}/{company.slug}/login"

    email_result = None
    if send_email:
        sent, detail = send_credentials_email(
            admin_email=admin.email,
            admin_name=admin.name,
            company_name=company.name,
            login_url=login_url,
            password=temporary_password,
        )
        email_result = {"sent": sent, "detail": detail}

    return {
        "company_id": company.id,
        "company_name": company.name,
        "slug": company.slug,
        "admin_name": admin.name,
        "admin_email": admin.email,
        "temporary_password": temporary_password,
        "login_url": login_url,
        "email_result": email_result,
    }
