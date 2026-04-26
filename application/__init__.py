from flask import Flask, flash, redirect, request, url_for
from db import db
from extensions import socketio, login_manager
from flask_migrate import Migrate
import os
import threading
import time
from flask_login import current_user, logout_user

from core.billing_service import process_pending_billing_events
from core.super_admin import is_super_admin_user

migrate = Migrate()








migrate = Migrate()

def create_app():

    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static"
    )

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "secret-key")

    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@db:5432/whatsapp_atendimento"
    )

    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # inicializar extensões
    db.init_app(app)
    migrate.init_app(app, db)

    socketio.init_app(app, cors_allowed_origins="*")
    login_manager.init_app(app)
    login_manager.login_view = "main.login"

     # importar models
    from models import (
        Conversation,
        Message,
        Notification,
        SLAEvent,
        User,
        Sector,
        Company,
        ConversationHistory,
        CompanySettings
    )
    from datetime import datetime
    
    @app.before_request
    def update_last_seen():
        if current_user.is_authenticated:

            now = datetime.utcnow()

            if not current_user.last_seen or (now - current_user.last_seen).seconds > 60:
                current_user.last_seen = now
                db.session.commit()

    @app.before_request
    def enforce_admin_password_change():
        if not current_user.is_authenticated:
            return

        # Super admin do Ops nao deve ficar bloqueado no fluxo de onboarding do cliente.
        if is_super_admin_user(current_user):
            return

        if current_user.role != "ADMIN" or not current_user.is_first_login:
            return

        allowed_endpoints = {
            "onboarding.change_password",
            "main.logout",
            "static",
        }

        endpoint = request.endpoint or ""

        if endpoint.startswith("ops."):
            return

        if endpoint in allowed_endpoints:
            return

        if endpoint.startswith("static"):
            return

        return redirect(url_for("onboarding.change_password"))

    @app.before_request
    def enforce_blocked_company():
        if not current_user.is_authenticated:
            return

        if is_super_admin_user(current_user):
            return

        endpoint = request.endpoint or ""
        if endpoint.startswith("ops."):
            return

        if endpoint in {"main.logout", "static"} or endpoint.startswith("static"):
            return

        settings = CompanySettings.query.filter_by(
            company_id=current_user.company_id
        ).first()
        if settings and settings.plan == "blocked":
            company_slug = current_user.company.slug if current_user.company else None
            logout_user()
            flash("Conta da empresa bloqueada. Fale com o suporte.", "warning")
            if company_slug:
                return redirect(url_for("main.tenant_login", company_slug=company_slug))
            return redirect(url_for("main.login"))

    @app.context_processor
    def inject_super_admin():
        return {
            "is_super_admin": is_super_admin_user(current_user) if current_user.is_authenticated else False
        }

    


   

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))
    
    
        # criar admin inicial
    from werkzeug.security import generate_password_hash
    
    
    # blueprints
    from application.routes.main import main_bp
    from application.routes.webhooks import webhooks_bp
    from application.routes.api_conversations import api_conv_bp
    from application.routes.api_metrics import api_metrics_bp
    from application.routes.api_sectors import api_sectors_bp
    from application.routes.api_upload import api_upload_bp, media_download_bp
    from application.routes.socket_events import register_socket_events
    from application.routes.admin import admin_bp
    from application.routes.admin_sectors import admin_sectors_bp
    from application.routes.admin_whatsapp_v2 import admin_whatsapp_bp
    from application.routes.onboarding import onboarding_bp
    from application.routes.api_whatsapp_v2 import api_whatsapp_bp
    from application.routes.dashboard import dashboard_bp
    from application.routes.ops import ops_bp
    from application.routes.commercial import commercial_bp


    app.register_blueprint(main_bp)
    app.register_blueprint(webhooks_bp)
    app.register_blueprint(api_conv_bp)
    app.register_blueprint(api_metrics_bp)
    app.register_blueprint(api_sectors_bp)
    app.register_blueprint(api_upload_bp)
    app.register_blueprint(media_download_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(admin_sectors_bp)
    app.register_blueprint(admin_whatsapp_bp)
    app.register_blueprint(onboarding_bp)
    app.register_blueprint(api_whatsapp_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(ops_bp)
    app.register_blueprint(commercial_bp)
    

    register_socket_events(socketio)

    def billing_worker():
        interval_seconds = int(os.getenv("BILLING_WORKER_INTERVAL_SECONDS", "5"))
        base_url = os.getenv("PLATFORM_BASE_URL", "http://localhost:5000").rstrip("/")
        while True:
            try:
                with app.app_context():
                    process_pending_billing_events(base_url=base_url, max_events=20)
            except Exception:
                pass
            time.sleep(max(interval_seconds, 1))

    billing_worker_enabled = os.getenv("BILLING_WORKER_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
    if billing_worker_enabled and not app.config.get("_BILLING_WORKER_STARTED"):
        threading.Thread(target=billing_worker, daemon=True).start()
        app.config["_BILLING_WORKER_STARTED"] = True

    return app
