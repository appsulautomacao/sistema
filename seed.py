import argparse
import os

from werkzeug.security import generate_password_hash

from application import create_app
from core.company_provisioning import (
    ensure_company_access_ready,
    provision_company_with_admin,
)
from core.super_admin import get_super_admin_emails
from db import db
from models import Company, CompanySettings, User


app = create_app()


def ensure_default_seed():
    company = Company.query.first()

    if not company:
        print("Criando empresa padrao...")
        company = Company(name="Empresa Padrao")
        db.session.add(company)
        db.session.flush()

    settings = CompanySettings.query.filter_by(company_id=company.id).first()
    if not settings:
        print("Criando configuracoes da empresa...")
        settings = CompanySettings(company_id=company.id)
        db.session.add(settings)

    admin = User.query.filter_by(email="admin@admin.com").first()
    if not admin:
        print("Criando usuario admin...")
        admin = User(
            name="Admin",
            email="admin@admin.com",
            password=generate_password_hash("123"),
            role="ADMIN",
            company_id=company.id,
        )
        db.session.add(admin)

    db.session.commit()
    ensure_company_access_ready(company)
    print("Seed finalizado.")


def ensure_super_admin(email=None, password=None, name="Appsul Admin"):
    selected_email = (email or "").strip().lower()
    if not selected_email:
        configured_emails = sorted(get_super_admin_emails())
        selected_email = configured_emails[0] if configured_emails else ""

    if not selected_email:
        raise ValueError("Informe --email ou configure SUPER_ADMIN_EMAILS.")

    selected_password = password or os.getenv("SUPER_ADMIN_INITIAL_PASSWORD")
    if not selected_password:
        selected_password = "TroqueEstaSenha@123"

    company = Company.query.filter_by(slug="appsul").first()
    if not company:
        company = Company(
            name="Appsul",
            slug="appsul",
            onboarding_completed=True,
            primary_color="#0D6EFD",
        )
        db.session.add(company)
        db.session.flush()

    settings = CompanySettings.query.filter_by(company_id=company.id).first()
    if not settings:
        settings = CompanySettings(company_id=company.id, plan="active")
        db.session.add(settings)
    else:
        settings.plan = "active"

    user = User.query.filter_by(email=selected_email).first()
    if not user:
        user = User(
            name=name,
            email=selected_email,
            password=generate_password_hash(selected_password),
            role="ADMIN",
            company_id=company.id,
            is_first_login=False,
            is_blocked=False,
        )
        db.session.add(user)
        action = "criado"
    else:
        user.name = user.name or name
        user.role = "ADMIN"
        user.company_id = company.id
        user.is_first_login = False
        user.is_blocked = False
        if password or os.getenv("SUPER_ADMIN_INITIAL_PASSWORD"):
            user.password = generate_password_hash(selected_password)
        action = "atualizado"

    db.session.commit()
    ensure_company_access_ready(company)

    print(f"Super admin {action}: {selected_email}")
    print("Login: /login")
    print(f"Senha: {selected_password}")


def parse_args():
    parser = argparse.ArgumentParser(description="Seed e provisionamento de clientes.")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("default", help="Executa seed padrao do projeto.")

    provision = subparsers.add_parser("provision-client", help="Cria empresa + admin inicial.")
    provision.add_argument("--company-name", required=True, help="Nome da empresa cliente.")
    provision.add_argument("--admin-name", default="Admin", help="Nome do usuario administrador.")
    provision.add_argument("--admin-email", required=True, help="E-mail do administrador.")
    provision.add_argument("--base-url", default="http://localhost:5000", help="URL base da plataforma.")
    provision.add_argument(
        "--send-email",
        action="store_true",
        help="Envia e-mail com credenciais via SMTP (se configurado).",
    )

    super_admin = subparsers.add_parser("super-admin", help="Cria/atualiza usuario super admin.")
    super_admin.add_argument("--email", help="E-mail do super admin. Padrao: primeiro SUPER_ADMIN_EMAILS.")
    super_admin.add_argument("--password", help="Senha inicial do super admin.")
    super_admin.add_argument("--name", default="Appsul Admin", help="Nome do super admin.")

    return parser.parse_args()


def main():
    args = parse_args()

    with app.app_context():
        if args.command in (None, "default"):
            ensure_default_seed()
            return

        if args.command == "provision-client":
            result = provision_company_with_admin(
                company_name=args.company_name,
                admin_name=args.admin_name,
                admin_email=args.admin_email,
                base_url=args.base_url,
                send_email=args.send_email,
            )

            print("Cliente provisionado com sucesso.")
            print(f"Empresa: {result['company_name']} (id={result['company_id']})")
            print(f"Slug: {result['slug']}")
            print(f"Admin: {result['admin_name']} <{result['admin_email']}>")
            print(f"Link: {result['login_url']}")
            print(f"Senha temporaria: {result['temporary_password']}")

            if result["email_result"] is not None:
                print(result["email_result"]["detail"])
                if not result["email_result"]["sent"]:
                    print("Credenciais acima devem ser enviadas manualmente ao cliente.")
            return

        if args.command == "super-admin":
            ensure_super_admin(
                email=args.email,
                password=args.password,
                name=args.name,
            )
            return


if __name__ == "__main__":
    main()
