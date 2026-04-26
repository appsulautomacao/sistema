import argparse

from werkzeug.security import generate_password_hash

from application import create_app
from core.company_provisioning import (
    ensure_company_access_ready,
    provision_company_with_admin,
)
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


if __name__ == "__main__":
    main()
