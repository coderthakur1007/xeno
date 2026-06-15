"""Pydantic request / response schemas for the Xeno API.

All schemas use Pydantic v2 ``BaseModel``.  Existing schemas are preserved;
new schemas for auth, pagination, typed responses, validated ingestion rows,
and webhook HMAC verification are appended below.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field, field_validator


# =====================================================================
# Existing schemas (preserved as-is)
# =====================================================================


class IngestCustomersRequest(BaseModel):
    rows: list[dict[str, Any]]


class IngestRowsRequest(BaseModel):
    rows: list[dict[str, Any]]


class SegmentCreateRequest(BaseModel):
    name: str
    source: str = Field(pattern="^(visual|natural_language)$")
    filters: dict[str, Any] = {}
    query: str | None = None


class GoalRequest(BaseModel):
    goal: str
    name: str | None = None


class WebhookEvent(BaseModel):
    """Inbound webhook from the channel simulator.

    ``signature`` carries the HMAC-SHA256 hex digest so the receiver can
    verify authenticity against the shared ``webhook_secret``.
    """

    tenant_id: str
    campaign_id: str | None = None
    message_id: str | None = None
    customer_id: str | None = None
    channel: str
    event_type: str
    provider_event_id: str | None = None
    metadata: dict[str, Any] = {}
    signature: str | None = None


class ApiEnvelope(BaseModel):
    data: Any
    meta: dict[str, Any] = {}


# =====================================================================
# Auth schemas
# =====================================================================


class LoginRequest(BaseModel):
    """Credentials for email + password login."""

    email: str
    password: str


class RegisterRequest(BaseModel):
    """New-user registration payload."""

    email: str
    password: str = Field(..., min_length=8, description="Minimum 8 characters")
    full_name: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    """JWT access-token response."""

    access_token: str
    token_type: str = "bearer"
    user: dict[str, Any]


class UserResponse(BaseModel):
    """Public representation of a user."""

    id: str
    email: str
    full_name: str
    role: str


# =====================================================================
# Paginated response (generic)
# =====================================================================

DataT = TypeVar("DataT")


class PaginatedResponse(BaseModel, Generic[DataT]):
    """Envelope for paginated list endpoints."""

    data: list[DataT]
    total: int
    page: int
    page_size: int


# =====================================================================
# Typed entity responses
# =====================================================================


class CampaignResponse(BaseModel):
    """Full campaign representation."""

    id: str
    tenant_id: str
    segment_id: str | None = None
    name: str
    goal: str
    status: str
    channels: list[str] = []
    strategy: dict[str, Any] = {}
    variants: list[Any] = []
    metrics: dict[str, Any] = {}
    created_by: str | None = None
    created_at: datetime | None = None
    launched_at: datetime | None = None

    model_config = {"from_attributes": True}


class SegmentResponse(BaseModel):
    """Full segment representation."""

    id: str
    tenant_id: str
    name: str
    description: str | None = None
    source: str
    filters: dict[str, Any] = {}
    sql_text: str
    estimated_size: int = 0
    created_by: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class AnalyticsOverviewResponse(BaseModel):
    """Typed metrics returned by the overview endpoint."""

    customers: int = 0
    orders: int = 0
    revenue: float = 0.0
    campaigns: int = 0


# =====================================================================
# Validated ingestion row schemas
# =====================================================================


class CustomerIngestRow(BaseModel):
    """A single customer record for bulk ingestion.

    ``external_id`` is required.  ``email`` is optional but validated when
    present.
    """

    external_id: str = Field(..., min_length=1)
    email: str | None = None
    phone: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    gender: str | None = None
    birth_date: str | None = None
    consent: dict[str, Any] = {}
    attributes: dict[str, Any] = {}

    @field_validator("email")
    @classmethod
    def _validate_email(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return v
        # Lightweight email check (no external dep required)
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email address")
        return v.strip().lower()


class OrderIngestRow(BaseModel):
    """A single order record for bulk ingestion."""

    external_id: str = Field(..., min_length=1)
    customer_id: str = Field(..., min_length=1)
    status: str = Field(..., min_length=1)
    total_amount: float = Field(..., ge=0)
    currency: str = Field(default="INR", max_length=8)
    channel: str = Field(..., min_length=1)
    items: list[Any] = []
    ordered_at: str  # ISO-8601 datetime string

    @field_validator("total_amount")
    @classmethod
    def _validate_amount(cls, v: float) -> float:
        if v < 0:
            raise ValueError("total_amount must not be negative")
        return round(v, 2)
