from flask import Blueprint, abort, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash

from models import Company, CompanySettings, User


main_bp = Blueprint("main", __name__)


def _post_login_redirect(user):
    settings = CompanySettings.query.filter_by(company_id=user.company_id).first()
    if settings and settings.plan == "blocked":
        return "Conta da empresa bloqueada. Fale com o suporte.", 403

    # ADMIN passa por primeiro acesso e onboarding.
    if user.role == "ADMIN":
        if user.is_first_login:
            return redirect(url_for("onboarding.change_password"))

        if not user.company.onboarding_completed:
            return redirect(url_for("onboarding.onboarding"))

    # AGENT/CENTRAL entram direto.
    return redirect(url_for("main.dashboard"))


@main_bp.route("/dashboard")
@login_required
def dashboard():
    # ADMIN tambem pode usar a central e acessar o administrativo pelo menu.
    if current_user.role == "ADMIN":
        return render_template(
            "dashboard.html",
            company=current_user.company
        )

    # Garante que tem setor.
    if not current_user.sector:
        return "Usuario sem setor definido", 400

    # CENTRAL (por flag) -> CHAT.
    if current_user.sector.is_central:
        return render_template(
            "dashboard.html",
            company=current_user.company
        )

    # Outros setores -> dashboard de setor.
    return render_template(
        "dashboard_setor.html",
        company=current_user.company
    )


@main_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            return _post_login_redirect(user)

        return "Credenciais invalidas", 401

    return render_template(
        "login.html",
        company=None,
        login_action=url_for("main.login"),
        login_title="Entrar na plataforma",
    )


@main_bp.route("/<company_slug>")
def tenant_root(company_slug):
    return redirect(url_for("main.tenant_login", company_slug=company_slug))


@main_bp.route("/<company_slug>/login", methods=["GET", "POST"])
def tenant_login(company_slug):
    company = Company.query.filter_by(slug=company_slug).first()
    if not company:
        return abort(404)

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        user = User.query.filter_by(email=email, company_id=company.id).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            return _post_login_redirect(user)

        return "Credenciais invalidas", 401

    return render_template(
        "login.html",
        company=company,
        login_action=url_for("main.tenant_login", company_slug=company.slug),
        login_title=f"Acessar {company.name}",
    )


@main_bp.route("/logout")
@login_required
def logout():
    company_slug = current_user.company.slug if current_user.company else None
    logout_user()
    if company_slug:
        return redirect(url_for("main.tenant_login", company_slug=company_slug))
    return redirect(url_for("main.login"))
