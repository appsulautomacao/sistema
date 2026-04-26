from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from db import db
from flask import abort
from werkzeug.security import generate_password_hash

onboarding_bp = Blueprint("onboarding", __name__)


@onboarding_bp.route("/onboarding/password", methods=["GET", "POST"])
@login_required
def change_password():
    if current_user.role != "ADMIN":
        return abort(403)

    if request.method == "POST":
        new_password = (request.form.get("new_password") or "").strip()
        confirm_password = (request.form.get("confirm_password") or "").strip()

        if len(new_password) < 8:
            flash("A nova senha deve ter no minimo 8 caracteres.", "warning")
            return redirect(url_for("onboarding.change_password"))

        if new_password != confirm_password:
            flash("As senhas nao conferem.", "warning")
            return redirect(url_for("onboarding.change_password"))

        current_user.password = generate_password_hash(new_password)
        current_user.is_first_login = False
        db.session.commit()

        flash("Senha atualizada com sucesso.", "success")
        return redirect(url_for("onboarding.onboarding"))

    return render_template("onboarding/change_password.html", wizard_step=1)


@onboarding_bp.route("/onboarding", methods=["GET", "POST"])
@login_required
def onboarding():
    if current_user.role != "ADMIN":
        return abort(403)
    if current_user.is_first_login:
        return redirect(url_for("onboarding.change_password"))

    step = request.args.get("step", "1")

    # STEP 1
    if request.method == "POST" and step == "1":
        company = current_user.company
        company.name = request.form.get("company_name")
        company.document = request.form.get("document")

        db.session.commit()

        return redirect(url_for("onboarding.onboarding", step=2))

    # STEP 2
    if step == "2":
        if not current_user.company.name:
            return redirect(url_for("onboarding.onboarding", step=1))

        return render_template(
            "onboarding/step2_whatsapp.html",
            wizard_step=2
        )

    return render_template(
        "onboarding/step1.html",
        wizard_step=1
    )


@onboarding_bp.route("/onboarding/finish", methods=["POST"])
@login_required
def finish_onboarding():
    if current_user.role != "ADMIN":
        return abort(403)

    current_user.company.onboarding_completed = True
    db.session.commit()

    return {"success": True}
