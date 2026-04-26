# app/models.py

from datetime import datetime
from flask_login import UserMixin
from core.datetime_utils import serialize_utc
from db import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120))
    email = db.Column(db.String(120), unique=True)
    password = db.Column(db.String(255))
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)
    role = db.Column(db.String(50), default="AGENT")  # ADMIN | CENTRAL | AGENT
    sector_id = db.Column(db.Integer, db.ForeignKey("sectors.id"), nullable=True)
    is_blocked = db.Column(db.Boolean, default=False)
    is_first_login = db.Column(db.Boolean, default=True)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)

    sector = db.relationship("Sector")
    presence = db.relationship("UserPresence", backref="user", uselist=False)

    @property
    def is_active(self):
        return not self.is_blocked

    @property
    def password_hash(self):
        return self.password

    @password_hash.setter
    def password_hash(self, value):
        self.password = value


class Sector(db.Model):
    __tablename__ = "sectors"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120))
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)
    sla_minutes = db.Column(db.Integer)
    is_central = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    company = db.relationship("Company", backref="sectors")


class Company(db.Model):
    __tablename__ = "companies"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(120), unique=True, index=True)
    document = db.Column(db.String(50))
    logo_url = db.Column(db.String(255))
    primary_color = db.Column(db.String(7), default="#0D6EFD")
    rag_document_path = db.Column(db.String(255))
    whatsapp_instance = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    onboarding_completed = db.Column(db.Boolean, default=False)
    users = db.relationship("User", backref="company", lazy=True)
    conversations = db.relationship("Conversation", backref="company", lazy=True)
    whatsapp_instances = db.relationship("WhatsAppInstance", backref="company", lazy=True)

    @property
    def active_whatsapp_instance(self):
        return next(
            (
                instance for instance in self.whatsapp_instances
                if instance.status != "deleted"
            ),
            None
        )

class CompanySettings(db.Model):
    __tablename__ = "company_settings"

    id = db.Column(db.Integer, primary_key=True)

    company_id = db.Column(
        db.Integer,
        db.ForeignKey("companies.id"),
        nullable=False,
        unique=True
    )

    sector_id = db.Column(
        db.Integer,
        db.ForeignKey("sectors.id"),
        index=True
    )

    # SLA padrão em minutos
    sla_minutes = db.Column(db.Integer, default=30)

    # horário comercial
    business_hours_start = db.Column(db.Time)
    business_hours_end = db.Column(db.Time)

    # distribuição automática
    auto_assign = db.Column(db.Boolean, default=False)

    # plano da empresa
    plan = db.Column(db.String(50), default="trial")

    # alerta antes do SLA estourar
    sla_alert_minutes = db.Column(db.Integer, default=5)

    company = db.relationship("Company", backref=db.backref("settings", uselist=False))
    central_ai_enabled = db.Column(db.Boolean, default=False)
    ai_classifier_model = db.Column(db.String(120), default="gpt-4o-mini")
    ai_classifier_prompt = db.Column(db.Text, nullable=True)
    ai_assistant_model = db.Column(db.String(120), default="gpt-4o-mini")
    ai_assistant_prompt = db.Column(db.Text, nullable=True)

    @property
    def central_sector_id(self):
        return self.sector_id

    @central_sector_id.setter
    def central_sector_id(self, value):
        self.sector_id = value

    @property
    def default_sla_minutes(self):
        return self.sla_minutes

    @default_sla_minutes.setter
    def default_sla_minutes(self, value):
        self.sla_minutes = value

class Conversation(db.Model):
    __tablename__ = "conversations"

    id = db.Column(db.Integer, primary_key=True)
    client_name = db.Column(db.String(120))
    client_phone = db.Column(db.String(50))
    status = db.Column(db.String(50), default="open")

    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)

    is_read = db.Column(db.Boolean, default=True)

    sector_id = db.Column(db.Integer, db.ForeignKey("sectors.id"))
    current_sector_id = db.Column(db.Integer, db.ForeignKey("sectors.id"), nullable=True)
    assigned_to = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    last_message_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    sector = db.relationship("Sector", foreign_keys=[sector_id])
    current_sector = db.relationship("Sector", foreign_keys=[current_sector_id])
    agent = db.relationship("User")

    @property
    def channel(self):
        return "whatsapp"


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id"))
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True, index=True)
    sender_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    sender = db.Column(db.String(50))
    sender_type = db.Column(db.String(50), nullable=True)
    content = db.Column(db.Text)
    type = db.Column(db.String(50), default="text")
    message_type = db.Column(db.String(50), nullable=True)
    media_url = db.Column(db.Text, nullable=True)
    external_message_id = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    conversation = db.relationship("Conversation")
    sender_user = db.relationship("User")
    attachments = db.relationship(
        "MessageAttachment",
        back_populates="message",
        cascade="all, delete-orphan",
        order_by="MessageAttachment.created_at.asc()",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "sender": self.sender_type or self.sender,
            "sender_type": self.sender_type or self.sender,
            "sender_user_id": self.sender_user_id,
            "content": self.content,
            "type": self.message_type or self.type,
            "message_type": self.message_type or self.type,
            "media_url": self.media_url,
            "attachments": [attachment.to_dict() for attachment in self.attachments],
            "company_id": self.company_id or (self.conversation.company_id if self.conversation else None),
            "created_at": serialize_utc(self.created_at)
        }


class MessageAttachment(db.Model):
    __tablename__ = "message_attachments"

    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey("messages.id"), nullable=False, index=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id"), nullable=False, index=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    provider = db.Column(db.String(50), nullable=True)
    provider_message_id = db.Column(db.String(255), nullable=True, index=True)
    provider_media_url = db.Column(db.Text, nullable=True)
    storage_backend = db.Column(db.String(30), nullable=False, default="local")
    storage_key = db.Column(db.String(512), nullable=True)
    original_filename = db.Column(db.String(255), nullable=True)
    safe_filename = db.Column(db.String(255), nullable=True)
    mime_type = db.Column(db.String(120), nullable=True)
    extension = db.Column(db.String(32), nullable=True)
    size_bytes = db.Column(db.BigInteger, nullable=True)
    checksum_sha256 = db.Column(db.String(64), nullable=True)
    attachment_type = db.Column(db.String(50), nullable=False, default="document")
    download_status = db.Column(db.String(30), nullable=False, default="pending")
    download_attempts = db.Column(db.Integer, nullable=False, default=0)
    download_error = db.Column(db.Text, nullable=True)
    is_inbound = db.Column(db.Boolean, nullable=False, default=True)
    downloaded_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    downloaded_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    processed_at = db.Column(db.DateTime, nullable=True)

    message = db.relationship("Message", back_populates="attachments")
    conversation = db.relationship("Conversation")
    company = db.relationship("Company")
    downloaded_by = db.relationship("User", foreign_keys=[downloaded_by_user_id])

    def to_dict(self):
        return {
            "id": self.id,
            "message_id": self.message_id,
            "conversation_id": self.conversation_id,
            "company_id": self.company_id,
            "provider": self.provider,
            "provider_message_id": self.provider_message_id,
            "provider_media_url": self.provider_media_url,
            "storage_backend": self.storage_backend,
            "storage_key": self.storage_key,
            "original_filename": self.original_filename,
            "safe_filename": self.safe_filename,
            "mime_type": self.mime_type,
            "extension": self.extension,
            "size_bytes": self.size_bytes,
            "attachment_type": self.attachment_type,
            "download_status": self.download_status,
            "download_attempts": self.download_attempts,
            "download_error": self.download_error,
            "is_inbound": self.is_inbound,
            "downloaded_by_user_id": self.downloaded_by_user_id,
            "downloaded_at": serialize_utc(self.downloaded_at),
            "expires_at": serialize_utc(self.expires_at),
            "created_at": serialize_utc(self.created_at),
            "processed_at": serialize_utc(self.processed_at),
            "download_url": f"/api/attachments/{self.id}/download",
        }


class AILog(db.Model):
    __tablename__ = "ai_logs"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id"))
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True, index=True)
    input_text = db.Column(db.Text)
    predicted_sector = db.Column(db.String(50))
    provider = db.Column(db.String(50), nullable=True)
    model_name = db.Column(db.String(120), nullable=True)
    used_fallback = db.Column(db.Boolean, default=False, nullable=False)
    raw_output = db.Column(db.Text, nullable=True)
    failure_reason = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class WhatsAppInstance(db.Model):
    __tablename__ = "whatsapp_instances"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    provider = db.Column(db.String(50), nullable=False, default="evolution")
    instance_name = db.Column(db.String(120), nullable=False, unique=True)
    api_key = db.Column(db.String(255), nullable=True)
    webhook_secret = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(50), nullable=False, default="created")
    last_connection_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class UserPresence(db.Model):
    __tablename__ = "user_presence"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    sector_id = db.Column(db.Integer, db.ForeignKey("sectors.id"), nullable=True, index=True)
    status = db.Column(db.String(30), nullable=False, default="offline")
    socket_session_id = db.Column(db.String(120), nullable=True)
    last_heartbeat_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    company = db.relationship("Company", backref="presences")
    sector = db.relationship("Sector")


class SLAEvent(db.Model):
    __tablename__ = "sla_events"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id"), nullable=False)

    event_type = db.Column(db.String(50))  # started | breached | resolved
    expected_response_at = db.Column(db.DateTime, nullable=False)
    actual_response_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    conversation = db.relationship("Conversation", backref="sla_events")


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id"), nullable=False)

    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(50))  # sla_warning | sla_breach | system

    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    conversation = db.relationship("Conversation", backref="notifications")


class ConversationHistory(db.Model):
    __tablename__ = "conversation_history"

    id = db.Column(db.Integer, primary_key=True)

    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id"), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    sector_id = db.Column(db.Integer, db.ForeignKey("sectors.id"), nullable=True)
    from_sector_id = db.Column(db.Integer, db.ForeignKey("sectors.id"), nullable=True)
    to_sector_id = db.Column(db.Integer, db.ForeignKey("sectors.id"), nullable=True)

    action_type = db.Column(db.String(50), nullable=False)
    event_type = db.Column(db.String(50), nullable=True)
    metadata_json = db.Column(db.JSON, nullable=True)

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True
    )


class ConversationRouting(db.Model):
    __tablename__ = "conversation_routings"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id"), nullable=False, index=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    sector_id = db.Column(db.Integer, db.ForeignKey("sectors.id"), nullable=False, index=True)
    assigned_to = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    transferred_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    transfer_reason = db.Column(db.String(255), nullable=True)
    entered_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    left_at = db.Column(db.DateTime, nullable=True)

    conversation = db.relationship("Conversation", backref="routings")
    company = db.relationship("Company", backref="conversation_routings")
    sector = db.relationship("Sector")
    assigned_user = db.relationship("User", foreign_keys=[assigned_to])
    transferred_by_user = db.relationship("User", foreign_keys=[transferred_by])


class BillingEvent(db.Model):
    __tablename__ = "billing_events"

    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(50), nullable=False, index=True)
    dedupe_key = db.Column(db.String(255), nullable=False, unique=True, index=True)
    external_event_id = db.Column(db.String(255), nullable=True, index=True)
    event_type = db.Column(db.String(120), nullable=True)
    payment_status = db.Column(db.String(80), nullable=True, index=True)
    reference = db.Column(db.String(255), nullable=True, index=True)
    checkout_session_id = db.Column(db.Integer, db.ForeignKey("checkout_sessions.id"), nullable=True, index=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True, index=True)
    company_name = db.Column(db.String(120), nullable=True)
    admin_name = db.Column(db.String(120), nullable=True)
    admin_email = db.Column(db.String(120), nullable=True, index=True)
    plan_code = db.Column(db.String(80), nullable=True, index=True)
    billing_period = db.Column(db.String(40), nullable=True)
    payment_method = db.Column(db.String(40), nullable=True)
    installment_count = db.Column(db.Integer, nullable=True)
    amount_cents = db.Column(db.Integer, nullable=True)
    payload_json = db.Column(db.JSON, nullable=True)
    processed = db.Column(db.Boolean, nullable=False, default=False)
    processing_error = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    processed_at = db.Column(db.DateTime, nullable=True)

    company = db.relationship("Company")
    checkout_session = db.relationship("CheckoutSession", back_populates="billing_events")


class BillingPlan(db.Model):
    __tablename__ = "billing_plans"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(80), nullable=False, unique=True, index=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)
    billing_period = db.Column(db.String(40), nullable=False, default="monthly", index=True)
    billing_cycle_months = db.Column(db.Integer, nullable=False, default=1)
    price_cents = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(10), nullable=False, default="BRL")
    setup_fee_cents = db.Column(db.Integer, nullable=False, default=0)
    max_installments = db.Column(db.Integer, nullable=False, default=1)
    allow_pix = db.Column(db.Boolean, nullable=False, default=True)
    allow_boleto = db.Column(db.Boolean, nullable=False, default=False)
    allow_card = db.Column(db.Boolean, nullable=False, default=True)
    is_public = db.Column(db.Boolean, nullable=False, default=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    highlight_text = db.Column(db.String(120), nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    metadata_json = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    checkout_sessions = db.relationship("CheckoutSession", back_populates="plan")
    subscriptions = db.relationship("Subscription", back_populates="plan")

    @property
    def price_display(self):
        value = (self.price_cents or 0) / 100
        return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


class CheckoutSession(db.Model):
    __tablename__ = "checkout_sessions"

    id = db.Column(db.Integer, primary_key=True)
    public_token = db.Column(db.String(64), nullable=False, unique=True, index=True)
    plan_id = db.Column(db.Integer, db.ForeignKey("billing_plans.id"), nullable=False, index=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True, index=True)
    company_name = db.Column(db.String(120), nullable=False)
    admin_name = db.Column(db.String(120), nullable=False)
    admin_email = db.Column(db.String(120), nullable=False, index=True)
    customer_document = db.Column(db.String(50), nullable=True)
    payment_method = db.Column(db.String(40), nullable=False, default="card")
    installment_count = db.Column(db.Integer, nullable=False, default=1)
    amount_cents = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(10), nullable=False, default="BRL")
    status = db.Column(db.String(40), nullable=False, default="created", index=True)
    provider = db.Column(db.String(50), nullable=False, default="pagseguro")
    external_checkout_id = db.Column(db.String(255), nullable=True, index=True)
    success_url = db.Column(db.String(500), nullable=True)
    cancel_url = db.Column(db.String(500), nullable=True)
    metadata_json = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)

    company = db.relationship("Company")
    plan = db.relationship("BillingPlan", back_populates="checkout_sessions")
    subscription = db.relationship("Subscription", back_populates="checkout_session", uselist=False)
    billing_events = db.relationship("BillingEvent", back_populates="checkout_session")
    payment_transactions = db.relationship("PaymentTransaction", back_populates="checkout_session")


class Subscription(db.Model):
    __tablename__ = "subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    plan_id = db.Column(db.Integer, db.ForeignKey("billing_plans.id"), nullable=False, index=True)
    checkout_session_id = db.Column(db.Integer, db.ForeignKey("checkout_sessions.id"), nullable=True, index=True)
    provider = db.Column(db.String(50), nullable=False, default="pagseguro")
    external_subscription_id = db.Column(db.String(255), nullable=True, index=True)
    status = db.Column(db.String(40), nullable=False, default="pending", index=True)
    billing_period = db.Column(db.String(40), nullable=False, default="monthly")
    amount_cents = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(10), nullable=False, default="BRL")
    started_at = db.Column(db.DateTime, nullable=True)
    current_period_start = db.Column(db.DateTime, nullable=True)
    current_period_end = db.Column(db.DateTime, nullable=True)
    cancel_at_period_end = db.Column(db.Boolean, nullable=False, default=False)
    canceled_at = db.Column(db.DateTime, nullable=True)
    metadata_json = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    company = db.relationship("Company")
    plan = db.relationship("BillingPlan", back_populates="subscriptions")
    checkout_session = db.relationship("CheckoutSession", back_populates="subscription", foreign_keys=[checkout_session_id])
    payment_transactions = db.relationship("PaymentTransaction", back_populates="subscription")


class PaymentTransaction(db.Model):
    __tablename__ = "payment_transactions"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True, index=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey("subscriptions.id"), nullable=True, index=True)
    checkout_session_id = db.Column(db.Integer, db.ForeignKey("checkout_sessions.id"), nullable=True, index=True)
    billing_event_id = db.Column(db.Integer, db.ForeignKey("billing_events.id"), nullable=True, index=True)
    provider = db.Column(db.String(50), nullable=False, default="pagseguro")
    external_payment_id = db.Column(db.String(255), nullable=True, index=True)
    payment_method = db.Column(db.String(40), nullable=True)
    installment_count = db.Column(db.Integer, nullable=True)
    amount_cents = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(10), nullable=False, default="BRL")
    status = db.Column(db.String(40), nullable=False, default="pending", index=True)
    paid_at = db.Column(db.DateTime, nullable=True)
    payload_json = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    company = db.relationship("Company")
    subscription = db.relationship("Subscription", back_populates="payment_transactions")
    checkout_session = db.relationship("CheckoutSession", back_populates="payment_transactions")
    billing_event = db.relationship("BillingEvent")


