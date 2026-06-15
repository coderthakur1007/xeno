import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[uuid.UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(Text)
    plan: Mapped[str] = mapped_column(String(32), default="growth")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[uuid.UUID] = mapped_column(String(36), ForeignKey("tenants.id"))
    email: Mapped[str] = mapped_column(Text, unique=True)
    full_name: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(32))
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdminSetting(Base):
    __tablename__ = "admin_settings"
    id: Mapped[uuid.UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[uuid.UUID] = mapped_column(String(36), ForeignKey("tenants.id"))
    key: Mapped[str] = mapped_column(Text)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FeatureFlag(Base):
    __tablename__ = "feature_flags"
    id: Mapped[uuid.UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[uuid.UUID] = mapped_column(String(36), ForeignKey("tenants.id"))
    key: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict)


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"
    id: Mapped[uuid.UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[uuid.UUID] = mapped_column(String(36), ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(default=1)
    template: Mapped[str] = mapped_column(Text)
    variables: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[uuid.UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[uuid.UUID] = mapped_column(String(36), ForeignKey("tenants.id"))
    external_id: Mapped[str] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    first_name: Mapped[str | None] = mapped_column(Text)
    last_name: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(Text)
    gender: Mapped[str | None] = mapped_column(Text)
    birth_date: Mapped[datetime | None] = mapped_column(Date)
    consent: Mapped[dict] = mapped_column(JSON, default=dict)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[uuid.UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[uuid.UUID] = mapped_column(String(36), ForeignKey("tenants.id"))
    customer_id: Mapped[uuid.UUID] = mapped_column(String(36), ForeignKey("customers.id"))
    external_id: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32))
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    channel: Mapped[str] = mapped_column(String(32))
    items: Mapped[list] = mapped_column(JSON, default=list)
    ordered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[uuid.UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[uuid.UUID] = mapped_column(String(36), ForeignKey("tenants.id"))
    customer_id: Mapped[uuid.UUID] = mapped_column(String(36), ForeignKey("customers.id"))
    order_id: Mapped[uuid.UUID | None] = mapped_column(String(36), ForeignKey("orders.id"))
    type: Mapped[str] = mapped_column(String(32))
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(32))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CommunicationEvent(Base):
    __tablename__ = "communication_events"
    id: Mapped[uuid.UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[uuid.UUID] = mapped_column(String(36), ForeignKey("tenants.id"))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(String(36), ForeignKey("customers.id"))
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(String(36))
    message_id: Mapped[uuid.UUID | None] = mapped_column(String(36))
    channel: Mapped[str] = mapped_column(String(32))
    event_type: Mapped[str] = mapped_column(String(32))
    provider_event_id: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Segment(Base):
    __tablename__ = "segments"
    id: Mapped[uuid.UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[uuid.UUID] = mapped_column(String(36), ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32))
    filters: Mapped[dict] = mapped_column(JSON, default=dict)
    sql_text: Mapped[str] = mapped_column(Text)
    estimated_size: Mapped[int] = mapped_column(default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Campaign(Base):
    __tablename__ = "campaigns"
    id: Mapped[uuid.UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[uuid.UUID] = mapped_column(String(36), ForeignKey("tenants.id"))
    segment_id: Mapped[uuid.UUID | None] = mapped_column(String(36), ForeignKey("segments.id"))
    name: Mapped[str] = mapped_column(Text)
    goal: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    channels: Mapped[list[str]] = mapped_column(JSON, default=list)
    strategy: Mapped[dict] = mapped_column(JSON, default=dict)
    variants: Mapped[list] = mapped_column(JSON, default=list)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    launched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    segment = relationship("Segment")


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[uuid.UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[uuid.UUID] = mapped_column(String(36), ForeignKey("tenants.id"))
    campaign_id: Mapped[uuid.UUID] = mapped_column(String(36), ForeignKey("campaigns.id"))
    customer_id: Mapped[uuid.UUID] = mapped_column(String(36), ForeignKey("customers.id"))
    channel: Mapped[str] = mapped_column(String(32))
    variant_key: Mapped[str] = mapped_column(String(32))
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    provider_message_id: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[uuid.UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(String(36), ForeignKey("tenants.id"))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(String(36), ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(Text)
    resource_type: Mapped[str] = mapped_column(Text)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(String(36))
    before: Mapped[dict | None] = mapped_column(JSON)
    after: Mapped[dict | None] = mapped_column(JSON)
    ip_address: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelRegistry(Base):
    __tablename__ = "model_registry"
    id: Mapped[uuid.UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[uuid.UUID] = mapped_column(String(36), ForeignKey("tenants.id"))
    model_name: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32))
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    feature_set: Mapped[dict] = mapped_column(JSON, default=dict)
    artifact_uri: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
