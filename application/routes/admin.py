import os

from flask import Blueprint, render_template, request, redirect, url_for
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
from flask import flash
from flask import jsonify
from models import Conversation, Message
from sqlalchemy import func

from db import db
from core.company_identity import (
    generate_unique_company_slug,
    normalize_brand_color,
    slugify_company_name,
)
from models import AILog, Company, CompanySettings, User, Sector, ConversationHistory, SLAEvent
from core.history import build_routing_audit
from core.assistant_ai import generate_company_assistant_reply
from core.metrics import get_sector_handoff_analytics
from core.rag import search_company_rag

from datetime import datetime,timedelta


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
RAG_UPLOAD_BASE_DIR = "files_rag"
RAG_ALLOWED_EXTENSIONS = {"txt", "md", "csv"}
LOGO_ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "svg"}
LOGO_UPLOAD_BASE_DIR = "static/uploads"


def ensure_central_sector(company_id):
    central = Sector.query.filter(
        Sector.company_id == company_id,
        func.lower(Sector.name) == "central"
    ).first()

    if central:
        if not central.is_central:
            central.is_central = True
            db.session.commit()
        return central

    central = Sector(
        name="Central",
        company_id=company_id,
        is_central=True,
        is_active=True
    )
    db.session.add(central)
    db.session.flush()

    settings = CompanySettings.query.filter_by(company_id=company_id).first()
    if not settings:
        settings = CompanySettings(company_id=company_id)
        db.session.add(settings)
    settings.central_sector_id = central.id

    db.session.commit()
    return central


def parse_time(value):
    from datetime import datetime
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError:
        return datetime.strptime(value, "%H:%M:%S").time()


@admin_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():

    # apenas ADMIN pode acessar
    if current_user.role != "ADMIN":
        return "Acesso negado", 403

    settings = CompanySettings.query.filter_by(
        company_id=current_user.company_id
    ).first()

    if not current_user.company.slug:
        current_user.company.slug = generate_unique_company_slug(
            current_user.company.name,
            exclude_company_id=current_user.company.id
        )
        db.session.commit()

    # Garante que settings existe.
    if not settings:
        settings = CompanySettings(company_id=current_user.company_id)
        db.session.add(settings)
        db.session.commit()

    ensure_central_sector(current_user.company_id)

    if request.method == "POST":
        company_name = (request.form.get("company_name") or "").strip()
        company_slug = (request.form.get("company_slug") or "").strip().lower()
        logo_url = (request.form.get("logo_url") or "").strip() or None
        primary_color_raw = request.form.get("primary_color")

        if not company_name:
            flash("Informe o nome da empresa.", "warning")
            return redirect(url_for("admin.settings"))

        if company_slug:
            company_slug = slugify_company_name(company_slug)
        else:
            company_slug = generate_unique_company_slug(
                company_name,
                exclude_company_id=current_user.company.id
            )

        existing_company = Company.query.filter_by(slug=company_slug).first()
        if existing_company and existing_company.id != current_user.company.id:
            flash("Este slug ja esta em uso. Escolha outro.", "warning")
            return redirect(url_for("admin.settings"))

        primary_color = normalize_brand_color(primary_color_raw)
        if primary_color is None:
            flash("Cor principal invalida. Use formato #RRGGBB.", "warning")
            return redirect(url_for("admin.settings"))

        logo_file = request.files.get("company_logo")
        if logo_file and logo_file.filename:
            safe_logo_name = secure_filename(logo_file.filename)
            ext = safe_logo_name.rsplit(".", 1)[-1].lower() if "." in safe_logo_name else ""
            if ext not in LOGO_ALLOWED_EXTENSIONS:
                flash("Formato de logo nao suportado. Use PNG, JPG, JPEG, WEBP ou SVG.", "warning")
                return redirect(url_for("admin.settings"))

            company_logo_dir = os.path.join(
                os.getcwd(),
                LOGO_UPLOAD_BASE_DIR,
                f"company_{current_user.company_id}",
                "branding",
            )
            os.makedirs(company_logo_dir, exist_ok=True)

            logo_filename = f"logo_company_{current_user.company_id}.{ext}"
            logo_path = os.path.join(company_logo_dir, logo_filename)
            logo_file.save(logo_path)
            logo_url = f"/static/uploads/company_{current_user.company_id}/branding/{logo_filename}"

        current_user.company.name = company_name
        current_user.company.slug = company_slug
        current_user.company.logo_url = logo_url
        current_user.company.primary_color = primary_color
        current_user.company.document = (request.form.get("document") or "").strip() or None

        current_user.company.rag_document_path = (request.form.get("rag_document_path") or "").strip() or None

        if "sla_minutes" in request.form:
            settings.sla_minutes = int(request.form.get("sla_minutes") or 0)

        start = request.form.get("business_hours_start")
        end = request.form.get("business_hours_end")

        if start and start.strip():
            settings.business_hours_start = parse_time(start)

        if end and end.strip():
            settings.business_hours_end = parse_time(end)

        if "auto_assign" in request.form:
            settings.auto_assign = True
        elif "settings_basic_form" in request.form:
            settings.auto_assign = False

        if "plan" in request.form:
            settings.plan = request.form.get("plan")

        if "sla_alert_minutes" in request.form:
            settings.sla_alert_minutes = int(request.form.get("sla_alert_minutes") or 0)

        if "central_ai_enabled" in request.form or "settings_basic_form" in request.form:
            settings.central_ai_enabled = "central_ai_enabled" in request.form

        if "ai_classifier_model" in request.form:
            settings.ai_classifier_model = (request.form.get("ai_classifier_model") or "gpt-4o-mini").strip()
        if "ai_classifier_prompt" in request.form:
            settings.ai_classifier_prompt = (request.form.get("ai_classifier_prompt") or "").strip() or None
        if "ai_assistant_model" in request.form:
            settings.ai_assistant_model = (request.form.get("ai_assistant_model") or "gpt-4o-mini").strip()
        if "ai_assistant_prompt" in request.form:
            settings.ai_assistant_prompt = (request.form.get("ai_assistant_prompt") or "").strip() or None

        db.session.commit()
        flash("Configurações da empresa atualizadas com sucesso.", "success")

        # Redireciona corretamente.
        return redirect("/admin")

    return render_template(
        "admin/settings.html",
        settings=settings,
        company=current_user.company,
        wizard_step=3
    )


@admin_bp.route("/rag/upload", methods=["POST"])
@login_required
def upload_rag_file():

    if current_user.role != "ADMIN":
        return "Acesso negado", 403

    uploaded_file = request.files.get("rag_file")
    if not uploaded_file or not uploaded_file.filename:
        flash("Selecione um arquivo para upload do RAG.", "warning")
        return redirect(url_for("admin.settings"))

    original_filename = secure_filename(uploaded_file.filename)
    if not original_filename:
        flash("Nome de arquivo inválido.", "warning")
        return redirect(url_for("admin.settings"))

    extension = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else ""
    if extension not in RAG_ALLOWED_EXTENSIONS:
        flash("Formato não suportado. Envie .txt, .md ou .csv.", "warning")
        return redirect(url_for("admin.settings"))

    company_dir = os.path.join(os.getcwd(), RAG_UPLOAD_BASE_DIR, f"company_{current_user.company_id}")
    os.makedirs(company_dir, exist_ok=True)

    destination_path = os.path.join(company_dir, original_filename)
    uploaded_file.save(destination_path)

    current_user.company.rag_document_path = os.path.join(
        RAG_UPLOAD_BASE_DIR,
        f"company_{current_user.company_id}",
        original_filename,
    ).replace("\\", "/")
    db.session.commit()

    flash("Arquivo de RAG enviado e vinculado à empresa com sucesso.", "success")
    return redirect(url_for("admin.settings"))

@admin_bp.route("/users")
@login_required
def users():

    if current_user.role != "ADMIN":
        return "Acesso negado", 403

    ensure_central_sector(current_user.company_id)

    users = User.query.filter_by(
        company_id=current_user.company_id
    ).all()

    sectors = Sector.query.filter_by(
        company_id=current_user.company_id
    ).all()

    return render_template(
        "admin/users.html",
        users=users,
        sectors=sectors
    )


@admin_bp.route("/ai-audit")
@login_required
def ai_audit():

    if current_user.role != "ADMIN":
        return "Acesso negado", 403

    query = AILog.query.filter_by(company_id=current_user.company_id)

    sector_filter = (request.args.get("sector") or "").strip()
    provider_filter = (request.args.get("provider") or "").strip()
    fallback_filter = (request.args.get("fallback") or "").strip().lower()
    search_filter = (request.args.get("q") or "").strip()

    if sector_filter:
        query = query.filter(AILog.predicted_sector == sector_filter)

    if provider_filter:
        query = query.filter(AILog.provider == provider_filter)

    if fallback_filter in {"yes", "no"}:
        query = query.filter(AILog.used_fallback == (fallback_filter == "yes"))

    if search_filter:
        query = query.filter(
            AILog.input_text.ilike(f"%{search_filter}%")
        )

    logs = query.order_by(AILog.created_at.desc()).limit(200).all()

    sector_options = [
        row[0] for row in db.session.query(AILog.predicted_sector)
        .filter(
            AILog.company_id == current_user.company_id,
            AILog.predicted_sector.isnot(None),
        )
        .distinct()
        .order_by(AILog.predicted_sector.asc())
        .all()
    ]

    provider_options = [
        row[0] for row in db.session.query(AILog.provider)
        .filter(
            AILog.company_id == current_user.company_id,
            AILog.provider.isnot(None),
        )
        .distinct()
        .order_by(AILog.provider.asc())
        .all()
    ]

    summary = {
        "total_logs": db.session.query(func.count(AILog.id)).filter(
            AILog.company_id == current_user.company_id
        ).scalar() or 0,
        "fallback_logs": db.session.query(func.count(AILog.id)).filter(
            AILog.company_id == current_user.company_id,
            AILog.used_fallback.is_(True),
        ).scalar() or 0,
        "provider_logs": db.session.query(func.count(AILog.id)).filter(
            AILog.company_id == current_user.company_id,
            AILog.provider.isnot(None),
            AILog.provider != "fallback",
        ).scalar() or 0,
    }

    return render_template(
        "admin/ai_audit.html",
        logs=logs,
        summary=summary,
        sector_options=sector_options,
        provider_options=provider_options,
        filters={
            "sector": sector_filter,
            "provider": provider_filter,
            "fallback": fallback_filter,
            "q": search_filter,
        },
    )


@admin_bp.route("/ai-rag")
@login_required
def ai_rag_preview():

    if current_user.role != "ADMIN":
        return "Acesso negado", 403

    query = (request.args.get("q") or "").strip()
    search_result = search_company_rag(current_user.company_id, query) if query else {
        "configured_path": current_user.company.rag_document_path,
        "results": [],
    }

    return render_template(
        "admin/ai_rag.html",
        company=current_user.company,
        query=query,
        search_result=search_result,
    )


@admin_bp.route("/ai-assistant", methods=["GET", "POST"])
@login_required
def ai_assistant_preview():

    if current_user.role != "ADMIN":
        return "Acesso negado", 403

    customer_message = ""
    preview = None

    if request.method == "POST":
        customer_message = (request.form.get("customer_message") or "").strip()
        if customer_message:
            preview = generate_company_assistant_reply(
                company_id=current_user.company_id,
                customer_message=customer_message,
                conversation_messages=[],
            )

    return render_template(
        "admin/ai_assistant.html",
        company=current_user.company,
        customer_message=customer_message,
        preview=preview,
    )


@admin_bp.route("/users/create", methods=["POST"])
@login_required
def create_user():

    if current_user.role != "ADMIN":
        return "Acesso negado", 403

    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    role = (request.form.get("role") or "AGENT").strip().upper()
    sector_id = (request.form.get("sector_id") or "").strip()

    if not name or not email or not password:
        flash("Preencha nome, email e senha para criar o usuario.", "warning")
        return redirect(url_for("admin.users"))

    if role not in {"ADMIN", "AGENT"}:
        flash("Perfil de usuario invalido.", "warning")
        return redirect(url_for("admin.users"))

    if not sector_id:
        flash("Cadastre um setor e selecione-o antes de criar usuarios.", "warning")
        return redirect(url_for("admin.users"))

    sector = Sector.query.filter_by(
        id=sector_id,
        company_id=current_user.company_id
    ).first()

    if not sector:
        flash("Setor invalido para esta empresa.", "warning")
        return redirect(url_for("admin.users"))

    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        flash("Ja existe um usuario com esse email.", "warning")
        return redirect(url_for("admin.users"))

    user = User(
        name=name,
        email=email,
        password=generate_password_hash(password),
        role=role,
        company_id=current_user.company_id,
        sector_id=sector.id
    )

    db.session.add(user)
    db.session.commit()

    flash("Usuario criado com sucesso.", "success")

    return redirect(url_for("admin.users"))


@admin_bp.route("/users/toggle/<int:user_id>", methods=["POST"])
@login_required
def toggle_user(user_id):

    if current_user.role != "ADMIN":
        return "Acesso negado", 403

    user = User.query.get_or_404(user_id)

    # impedir bloquear a si mesmo
    if user.id == current_user.id:
        flash("Você não pode bloquear seu próprio usuário.", "warning")
        return redirect(url_for("admin.users"))

    user.is_blocked = not user.is_blocked

    db.session.commit()

    return redirect(url_for("admin.users"))


@admin_bp.route("/users/delete/<int:user_id>")
@login_required
def delete_user(user_id):

    if current_user.role != "ADMIN":
        return "Acesso negado", 403

    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash("Não é possível excluir seu próprio usuário.", "warning")
        return redirect(url_for("admin.users"))

    # Verificar histórico.
    history = ConversationHistory.query.filter_by(
        user_id=user.id
    ).first()

    if history:

        flash(
            "Usuário possui histórico de conversas e não pode ser excluído. Apenas bloqueie.",
            "warning"
        )

        return redirect(url_for("admin.users"))

    db.session.delete(user)
    db.session.commit()

    flash("Usuário excluído com sucesso.", "success")

    return redirect(url_for("admin.users"))




@admin_bp.route("/")
@login_required
def admin_home():

    if current_user.role != "ADMIN":
        return redirect("/dashboard")

    company_id = current_user.company_id
    ensure_central_sector(company_id)
    today = datetime.utcnow().date()

    open_conversations = Conversation.query.filter_by(
        company_id=company_id,
        status="open"
    ).count()
    assigned_conversations = Conversation.query.filter(
        Conversation.company_id == company_id,
        Conversation.status == "open",
        Conversation.assigned_to.isnot(None)
    ).count()
    queue_conversations = Conversation.query.filter(
        Conversation.company_id == company_id,
        Conversation.status == "open",
        Conversation.assigned_to.is_(None)
    ).count()
    unread_conversations = Conversation.query.filter_by(
        company_id=company_id,
        is_read=False
    ).count()
    sla_breached = db.session.query(func.count(func.distinct(SLAEvent.conversation_id))).join(
        Conversation,
        Conversation.id == SLAEvent.conversation_id
    ).filter(
        Conversation.company_id == company_id,
        Conversation.status == "open",
        SLAEvent.event_type == "breached"
    ).scalar() or 0
    today_conversations = Conversation.query.filter(
        Conversation.company_id == company_id,
        func.date(Conversation.created_at) == today
    ).count()

    metrics = {
        "open_conversations": open_conversations,
        "total": Conversation.query.filter_by(company_id=company_id).count(),
        "sla_breached": sla_breached,
        "avg_response": 2
    }

    operational_summary = {
        "queue": queue_conversations,
        "assigned": assigned_conversations,
        "unread": unread_conversations,
        "sla": sla_breached,
        "today": today_conversations,
        "satisfaction": None,
    }

    ranking = db.session.query(
        User.name,
        func.count(Conversation.id).label("count")
    ).join(Conversation).filter(
        Conversation.company_id == company_id
    ).group_by(User.name).all()

    ranking = [{"name": r[0], "count": r[1]} for r in ranking]

    conversations_db = Conversation.query.filter_by(
        company_id=company_id
    ).order_by(Conversation.created_at.desc()).limit(10).all()

    conversations = []

    for c in conversations_db:
        last_msg = Message.query.filter_by(
            conversation_id=c.id
        ).order_by(Message.created_at.desc()).first()

        conversations.append({
            "contact": c.client_name or c.client_phone or "Sem nome",
            "last_message": last_msg.content if last_msg else "Sem mensagens"
        })

    sectors = Sector.query.filter_by(
        company_id=company_id
    ).all()
    handoff_analytics = get_sector_handoff_analytics(company_id)

    sector_operations = {}
    sector_user_map = {}
    for sector in sectors:
        sector_user_map[sector.id] = User.query.filter_by(
            company_id=company_id,
            sector_id=sector.id
        ).all()
        sector_operations[sector.id] = {
            "queue": Conversation.query.filter(
                Conversation.company_id == company_id,
                Conversation.status == "open",
                Conversation.current_sector_id == sector.id,
                Conversation.assigned_to.is_(None)
            ).count(),
            "assigned": Conversation.query.filter(
                Conversation.company_id == company_id,
                Conversation.status == "open",
                Conversation.current_sector_id == sector.id,
                Conversation.assigned_to.isnot(None)
            ).count(),
        }

    online_limit = datetime.utcnow() - timedelta(minutes=5)

    online_count = User.query.filter(
        User.company_id == company_id,
        User.last_seen != None,
        User.last_seen > online_limit
    ).count()

    recent_events = ConversationHistory.query.filter_by(
        company_id=company_id
    ).order_by(ConversationHistory.created_at.desc()).limit(6).all()

    volume_rows = db.session.query(
        func.date(Conversation.created_at).label("day"),
        func.count(Conversation.id).label("conversation_count")
    ).filter(
        Conversation.company_id == company_id,
        Conversation.created_at >= datetime.utcnow() - timedelta(days=6)
    ).group_by(func.date(Conversation.created_at)).order_by(func.date(Conversation.created_at)).all()

    volume_labels = [row.day.strftime("%d/%m") if hasattr(row.day, "strftime") else str(row.day) for row in volume_rows]
    volume_counts = [row.conversation_count for row in volume_rows]

    whatsapp_connected = True

    return render_template(
        "admin/dashboard.html",
        metrics=metrics,
        operational_summary=operational_summary,
        ranking=ranking,
        conversations=conversations,
        sectors=sectors,
        sector_operations=sector_operations,
        sector_user_map=sector_user_map,
        handoff_summary=handoff_analytics["summary"],
        handoff_paths=handoff_analytics["paths"][:8],
        handoff_sectors=handoff_analytics["sectors"][:8],
        central_handoff_summary=handoff_analytics["central"]["summary"],
        central_outbound_paths=handoff_analytics["central"]["outbound_paths"][:6],
        central_inbound_paths=handoff_analytics["central"]["inbound_paths"][:6],
        online_count=online_count,
        online_limit=online_limit,
        whatsapp_connected=whatsapp_connected,
        recent_events=recent_events,
        volume_labels=volume_labels,
        volume_counts=volume_counts,
    )



@admin_bp.route("/api/conversations")
@login_required
def search_conversations():

    if current_user.role != "ADMIN":
        return jsonify([])

    agent = request.args.get("agent")
    client = request.args.get("client")
    date = request.args.get("date")

    query = Conversation.query.filter_by(
        company_id=current_user.company_id
    )

    if agent:
        query = query.join(User, Conversation.assigned_to == User.id)\
                     .filter(User.name.ilike(f"%{agent}%"))

    if client:
        query = query.filter(
            db.or_(
                Conversation.client_name.ilike(f"%{client}%"),
                Conversation.client_phone.ilike(f"%{client}%")
            )
        )

    if date:
        query = query.filter(func.date(Conversation.created_at) == date)

    conversations = query.order_by(Conversation.created_at.desc()).limit(20).all()

    result = []

    for c in conversations:
        last_msg = Message.query.filter_by(
            conversation_id=c.id
        ).order_by(Message.created_at.desc()).first()

        result.append({
            "id": c.id,
            "client": c.client_name or c.client_phone,
            "agent": c.agent.name if c.agent else "Nao atribuido",
            "last_message": last_msg.content if last_msg else "",
            "date": c.created_at.strftime("%d/%m %H:%M")
        })

    return jsonify(result)



@admin_bp.route("/conversations/<int:conversation_id>")
@login_required
def conversation_detail(conversation_id):

    if current_user.role != "ADMIN":
        return {"error": "Acesso negado"}, 403

    conversation = Conversation.query.get_or_404(conversation_id)

    if conversation.company_id != current_user.company_id:
        return {"error": "Acesso negado"}, 403

    messages = Message.query.filter_by(
        conversation_id=conversation.id
    ).order_by(Message.created_at.asc()).all()

    return {
        "conversation": {
            "client": conversation.client_name or conversation.client_phone
        },
        "messages": [
            {
                "content": m.content,
                "from_me": (m.sender_type or m.sender) in ["agent", "ai"],
                "time": m.created_at.strftime("%d/%m %H:%M")
            }
            for m in messages
        ]
    }


@admin_bp.route("/conversations/<int:conversation_id>/routing")
@login_required
def conversation_routing(conversation_id):
    if current_user.role != "ADMIN":
        return {"error": "Acesso negado"}, 403

    conversation = Conversation.query.get_or_404(conversation_id)
    if conversation.company_id != current_user.company_id:
        return {"error": "Acesso negado"}, 403

    return jsonify(build_routing_audit(conversation))


@admin_bp.route("/sectors", methods=["GET", "POST"])
@login_required
def sectors():

    if current_user.role != "ADMIN":
        return "Acesso negado", 403

    ensure_central_sector(current_user.company_id)

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()

        if not name:
            flash("Informe o nome do setor.", "warning")
            return redirect(url_for("admin.sectors"))

        existing_sector = Sector.query.filter(
            Sector.company_id == current_user.company_id,
            func.lower(Sector.name) == name.lower()
        ).first()
        if existing_sector:
            flash("Ja existe um setor com esse nome.", "warning")
            return redirect(url_for("admin.sectors"))

        is_central = name.lower() == "central"

        sector = Sector(
            name=name,
            company_id=current_user.company_id,
            is_central=is_central
        )

        db.session.add(sector)
        db.session.flush()

        if is_central:
            settings = CompanySettings.query.filter_by(
                company_id=current_user.company_id
            ).first()
            if not settings:
                settings = CompanySettings(company_id=current_user.company_id)
                db.session.add(settings)
            settings.central_sector_id = sector.id

        db.session.commit()
        flash("Setor criado com sucesso.", "success")

        return redirect(url_for("admin.sectors"))

    sectors = Sector.query.filter_by(
        company_id=current_user.company_id
    ).all()

    return render_template(
        "admin/sectors.html",
        sectors=sectors
    )
