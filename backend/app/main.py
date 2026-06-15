"""Xeno AI Campaign Copilot — FastAPI application entry-point.

Integrates all core, domain, infrastructure, and service modules into a
single coherent API surface with JWT authentication, Redis-backed rate
limiting, background message delivery, Prometheus metrics, and HMAC
webhook verification.
"""

import csv
import hashlib
import hmac
import io
import json
import logging
import time
import uuid

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, ORJSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy import select
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Core imports
# ---------------------------------------------------------------------------
from app.core.config import Settings, get_settings
from app.core.database import Base, engine, get_db
from app.core.redis_client import CacheService, RateLimiter
from app.core.security import (
    create_access_token,
    get_current_user,
    hash_password,
    require_role,
    verify_password,
)
from app.core.worker import start_worker

# ---------------------------------------------------------------------------
# Domain imports
# ---------------------------------------------------------------------------
from app.domain.models import (
    AdminSetting,
    AuditLog,
    Campaign,
    CommunicationEvent,
    Customer,
    FeatureFlag,
    Message,
    ModelRegistry,
    Order,
    PromptTemplate,
    Segment,
    Tenant,
    Transaction,
    User,
)

# ---------------------------------------------------------------------------
# Infrastructure imports
# ---------------------------------------------------------------------------
from app.infrastructure.repositories import (
    AdminSettingRepository,
    AnalyticsRepository,
    AuditRepository,
    CampaignRepository,
    CustomerRepository,
    EventRepository,
    FeatureFlagRepository,
    IngestionRepository,
    PromptTemplateRepository,
    SegmentRepository,
    TenantRepository,
)

# ---------------------------------------------------------------------------
# Interface / schema imports
# ---------------------------------------------------------------------------
from app.interfaces.schemas import (
    GoalRequest,
    IngestCustomersRequest,
    IngestRowsRequest,
    LoginRequest,
    RegisterRequest,
    SegmentCreateRequest,
    TokenResponse,
    WebhookEvent,
)

# ---------------------------------------------------------------------------
# Service imports
# ---------------------------------------------------------------------------
from app.services.campaigns import CampaignService
from app.services.proofs import CopilotProofService
from app.services.segmentation import SegmentationService

# ---------------------------------------------------------------------------
# Agent imports
# ---------------------------------------------------------------------------
from app.agents.copilot import MarketingCopilotGraph

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("xeno.api")

# ===================================================================
# App setup
# ===================================================================

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="AI-powered campaign copilot for modern marketers",
    version="1.0.0",
    default_response_class=ORJSONResponse,
)

# Prometheus metrics
REQUESTS = Counter("xeno_api_requests_total", "API requests", ["path", "method", "status"])
LATENCY = Histogram("xeno_api_request_latency_seconds", "API request latency", ["path", "method"])

# CORS — origins from settings, split by comma
origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Redis-backed rate limiter (gracefully degrades if Redis is down)
rate_limiter = RateLimiter()

# ===================================================================
# Startup event
# ===================================================================


@app.on_event("startup")
def startup() -> None:
    """Create database tables and start the background message worker."""
    Base.metadata.create_all(bind=engine)
    start_worker(settings)
    logger.info("Xeno API started — %s", settings.app_name)


# ===================================================================
# Middleware — rate limiting + Prometheus metrics
# ===================================================================


@app.middleware("http")
async def observe(request: Request, call_next):
    """Per-request middleware: Redis rate limiting and Prometheus metrics."""
    start = time.perf_counter()

    # --- Rate limiting (Redis sliding window) ---
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limiter.check(client_ip, settings.rate_limit_per_minute, 60):
        return ORJSONResponse({"detail": "rate limit exceeded"}, status_code=429)

    response = await call_next(request)

    # --- Prometheus metrics ---
    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path)
    REQUESTS.labels(path=path, method=request.method, status=response.status_code).inc()
    LATENCY.labels(path=path, method=request.method).observe(time.perf_counter() - start)
    return response


# ===================================================================
# 1. Health & Metrics (no auth)
# ===================================================================


@app.get("/healthz")
def healthz():
    """Liveness probe."""
    return {"status": "ok", "service": settings.app_name}


@app.get("/metrics")
def metrics():
    """Prometheus metrics endpoint."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ===================================================================
# 2. Auth endpoints — /api/v1/auth
# ===================================================================


@app.post("/api/v1/auth/register", response_model=TokenResponse, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    """Register a new user (and tenant if first user)."""
    # Check for existing user
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    # Create or find a default tenant
    tenant = db.scalar(select(Tenant).limit(1))
    if not tenant:
        tenant = Tenant(name="Default Tenant")
        db.add(tenant)
        db.flush()

    user = User(
        tenant_id=tenant.id,
        email=payload.email,
        full_name=payload.full_name,
        role="admin" if not db.scalar(select(User).where(User.tenant_id == tenant.id).limit(1)) else "marketer",
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": str(user.id), "user_id": str(user.id), "tenant_id": str(user.tenant_id)})
    return TokenResponse(
        access_token=token,
        user={"id": str(user.id), "email": user.email, "full_name": user.full_name, "role": user.role},
    )


@app.post("/api/v1/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate with email + password and receive a JWT."""
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not user.password_hash or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    token = create_access_token({"sub": str(user.id), "user_id": str(user.id), "tenant_id": str(user.tenant_id)})
    return TokenResponse(
        access_token=token,
        user={"id": str(user.id), "email": user.email, "full_name": user.full_name, "role": user.role},
    )


@app.get("/api/v1/auth/me")
def me(user: User = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    return {
        "data": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "tenant_id": str(user.tenant_id),
        }
    }


# ===================================================================
# 3. Analytics endpoints (require auth)
# ===================================================================


@app.get("/api/v1/analytics/overview")
def overview(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return {"data": AnalyticsRepository(db).overview(user.tenant_id)}


@app.get("/api/v1/analytics/rfm")
def rfm(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return {"data": AnalyticsRepository(db).rfm(user.tenant_id)}


@app.get("/api/v1/analytics/cohorts")
def cohorts(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return {"data": AnalyticsRepository(db).cohorts(user.tenant_id)}


@app.get("/api/v1/analytics/customer-health")
def customer_health(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return {"data": AnalyticsRepository(db).customer_health(user.tenant_id)}


@app.get("/api/v1/campaigns/{campaign_id}/funnel")
def funnel(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return {"data": AnalyticsRepository(db).funnel(campaign_id)}


# ===================================================================
# 4. Ingestion endpoints (require auth)
# ===================================================================


@app.post("/api/v1/ingest/customers")
def ingest_customers(
    payload: IngestCustomersRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    count = CustomerRepository(db).upsert_many(user.tenant_id, payload.rows)
    AuditRepository(db).log(
        tenant_id=user.tenant_id, actor_id=user.id,
        action="ingest.customers", resource_type="customer",
        after={"count": count},
    )
    return {"data": {"ingested": count}}


@app.post("/api/v1/ingest/customers/csv")
async def ingest_customers_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    raw = (await file.read()).decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(raw)))
    count = CustomerRepository(db).upsert_many(user.tenant_id, rows)
    AuditRepository(db).log(
        tenant_id=user.tenant_id, actor_id=user.id,
        action="ingest.customers_csv", resource_type="customer",
        after={"count": count},
    )
    return {"data": {"ingested": count}}


@app.post("/api/v1/ingest/orders")
def ingest_orders(
    payload: IngestRowsRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    count = IngestionRepository(db).upsert_orders(user.tenant_id, payload.rows)
    AuditRepository(db).log(
        tenant_id=user.tenant_id, actor_id=user.id,
        action="ingest.orders", resource_type="order",
        after={"count": count},
    )
    return {"data": {"ingested": count}}


@app.post("/api/v1/ingest/transactions")
def ingest_transactions(
    payload: IngestRowsRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    count = IngestionRepository(db).add_transactions(user.tenant_id, payload.rows)
    return {"data": {"ingested": count}}


@app.post("/api/v1/ingest/communication-events")
def ingest_communication_events(
    payload: IngestRowsRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    count = IngestionRepository(db).add_events(user.tenant_id, payload.rows)
    return {"data": {"ingested": count}}


# ===================================================================
# 5. Segment endpoints (require auth)
# ===================================================================


@app.post("/api/v1/segments")
def create_segment(
    payload: SegmentCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    segment = SegmentationService(db).create_segment(
        user.tenant_id, user.id, payload.name, payload.source, payload.filters, payload.query,
    )
    AuditRepository(db).log(
        tenant_id=user.tenant_id, actor_id=user.id,
        action="segment.create", resource_type="segment",
        resource_id=segment.id, after={"name": segment.name},
    )
    return {
        "data": {
            "id": str(segment.id),
            "name": segment.name,
            "estimated_size": segment.estimated_size,
            "sql_text": segment.sql_text,
            "filters": segment.filters,
        }
    }


@app.get("/api/v1/segments")
def list_segments(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    offset = (page - 1) * page_size
    segments = SegmentRepository(db).recent(user.tenant_id, limit=page_size, offset=offset)
    return {
        "data": [
            {
                "id": str(s.id),
                "name": s.name,
                "source": s.source,
                "estimated_size": s.estimated_size,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in segments
        ]
    }


# ===================================================================
# 6. Copilot endpoints (require auth)
# ===================================================================


@app.post("/api/v1/copilot/plan")
def copilot_plan(
    payload: GoalRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return {"data": MarketingCopilotGraph(db).plan(user.tenant_id, payload.goal)}


@app.get("/api/v1/copilot/proof")
def copilot_proof(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return {"data": CopilotProofService(db).run_prompt_matrix(user.tenant_id)}


@app.get("/api/v1/reports/copilot-proof.xlsx")
def copilot_proof_excel(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    path = CopilotProofService(db).build_excel(user.tenant_id)
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="xeno_copilot_proof.xlsx",
    )


# ===================================================================
# 7. Campaign endpoints (require auth)
# ===================================================================


@app.post("/api/v1/campaigns/from-goal")
def campaign_from_goal(
    payload: GoalRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    campaign = CampaignService(db).draft_from_goal(user.tenant_id, user.id, payload.goal, payload.name)
    AuditRepository(db).log(
        tenant_id=user.tenant_id, actor_id=user.id,
        action="campaign.draft", resource_type="campaign",
        resource_id=campaign.id, after={"name": campaign.name},
    )
    return {
        "data": {
            "id": str(campaign.id),
            "name": campaign.name,
            "status": campaign.status,
            "channels": campaign.channels,
            "strategy": campaign.strategy,
            "variants": campaign.variants,
        }
    }


@app.get("/api/v1/campaigns")
def list_campaigns(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    offset = (page - 1) * page_size
    campaigns = CampaignRepository(db).list(user.tenant_id, limit=page_size, offset=offset)
    return {
        "data": [
            {
                "id": str(c.id),
                "name": c.name,
                "goal": c.goal,
                "status": c.status,
                "channels": c.channels,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "metrics": c.metrics,
            }
            for c in campaigns
        ]
    }


@app.get("/api/v1/campaigns/{campaign_id}")
def get_campaign(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    campaign = CampaignRepository(db).get(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {
        "data": {
            "id": str(campaign.id),
            "name": campaign.name,
            "goal": campaign.goal,
            "status": campaign.status,
            "channels": campaign.channels,
            "strategy": campaign.strategy,
            "variants": campaign.variants,
            "metrics": campaign.metrics,
            "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
            "launched_at": campaign.launched_at.isoformat() if campaign.launched_at else None,
        }
    }


@app.post("/api/v1/campaigns/{campaign_id}/launch")
def launch_campaign(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        result = CampaignService(db).launch(campaign_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    AuditRepository(db).log(
        tenant_id=user.tenant_id, actor_id=user.id,
        action="campaign.launch", resource_type="campaign",
        resource_id=campaign_id,
    )
    return {"data": result}


# ===================================================================
# 8. Admin endpoints (require admin role)
# ===================================================================


@app.get("/api/v1/admin/settings")
def admin_settings(
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    rows = db.scalars(
        select(AdminSetting)
        .where(AdminSetting.tenant_id == user.tenant_id)
        .order_by(AdminSetting.key)
    ).all()
    return {
        "data": [
            {"key": r.key, "value": r.value, "updated_at": r.updated_at.isoformat() if r.updated_at else None}
            for r in rows
        ]
    }


@app.put("/api/v1/admin/settings/{key}")
def upsert_setting(
    key: str,
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    existing = db.scalar(
        select(AdminSetting).where(AdminSetting.tenant_id == user.tenant_id, AdminSetting.key == key)
    )
    if existing:
        existing.value = payload
        from datetime import datetime, timezone
        existing.updated_at = datetime.now(timezone.utc)
    else:
        db.add(AdminSetting(tenant_id=user.tenant_id, key=key, value=payload))
    db.commit()
    AuditRepository(db).log(
        tenant_id=user.tenant_id, actor_id=user.id,
        action="admin.settings.upsert", resource_type="admin_setting",
        after={"key": key},
    )
    return {"data": {"key": key, "value": payload}}


@app.get("/api/v1/admin/feature-flags")
def feature_flags(
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    rows = db.scalars(
        select(FeatureFlag)
        .where(FeatureFlag.tenant_id == user.tenant_id)
        .order_by(FeatureFlag.key)
    ).all()
    return {"data": [{"key": r.key, "enabled": r.enabled, "config": r.config} for r in rows]}


@app.put("/api/v1/admin/feature-flags/{key}")
def toggle_feature_flag(
    key: str,
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    existing = db.scalar(
        select(FeatureFlag).where(FeatureFlag.tenant_id == user.tenant_id, FeatureFlag.key == key)
    )
    enabled = payload.get("enabled", True)
    config = payload.get("config", {})
    if existing:
        existing.enabled = enabled
        existing.config = config
    else:
        db.add(FeatureFlag(tenant_id=user.tenant_id, key=key, enabled=enabled, config=config))
    db.commit()
    AuditRepository(db).log(
        tenant_id=user.tenant_id, actor_id=user.id,
        action="admin.feature_flag.toggle", resource_type="feature_flag",
        after={"key": key, "enabled": enabled},
    )
    return {"data": {"key": key, "enabled": enabled, "config": config}}


@app.get("/api/v1/admin/prompt-templates")
def prompt_templates(
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    rows = db.scalars(
        select(PromptTemplate)
        .where(PromptTemplate.tenant_id == user.tenant_id)
        .order_by(PromptTemplate.name, PromptTemplate.version.desc())
    ).all()
    return {
        "data": [
            {
                "id": str(r.id),
                "name": r.name,
                "version": r.version,
                "template": r.template,
                "variables": r.variables,
                "is_active": r.is_active,
            }
            for r in rows
        ]
    }


@app.get("/api/v1/audit-logs")
def audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    offset = (page - 1) * page_size
    logs = AuditRepository(db).recent(user.tenant_id, limit=page_size, offset=offset)
    return {
        "data": [
            {
                "id": str(log.id),
                "action": log.action,
                "resource_type": log.resource_type,
                "resource_id": str(log.resource_id) if log.resource_id else None,
                "after": log.after,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ]
    }


# ===================================================================
# 9. Webhook endpoint (no auth, HMAC verification)
# ===================================================================


@app.post("/api/v1/webhooks/channel-events")
def channel_events(
    payload: WebhookEvent,
    db: Session = Depends(get_db),
    x_webhook_signature: str | None = Header(None),
):
    """Receive channel events from the simulator.

    If X-Webhook-Signature is present, verify HMAC-SHA256 against the
    configured webhook_secret.  If the header is absent, accept the
    request for backward compatibility.
    """
    if x_webhook_signature:
        body_bytes = json.dumps(payload.model_dump(), default=str, sort_keys=True).encode("utf-8")
        expected = hmac.new(
            settings.webhook_secret.encode("utf-8"), body_bytes, hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, x_webhook_signature):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    event = CommunicationEvent(
        tenant_id=uuid.UUID(payload.tenant_id),
        campaign_id=uuid.UUID(payload.campaign_id) if payload.campaign_id else None,
        message_id=uuid.UUID(payload.message_id) if payload.message_id else None,
        customer_id=uuid.UUID(payload.customer_id) if payload.customer_id else None,
        channel=payload.channel,
        event_type=payload.event_type,
        provider_event_id=payload.provider_event_id,
        metadata_=payload.metadata,
    )
    EventRepository(db).record(event)
    return {"data": {"accepted": True}}


# ===================================================================
# 10. Customer endpoints (require auth)
# ===================================================================


@app.get("/api/v1/customers")
def list_customers(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Paginated customer list for the current tenant."""
    offset = (page - 1) * page_size
    customers = db.scalars(
        select(Customer)
        .where(Customer.tenant_id == user.tenant_id)
        .order_by(Customer.created_at.desc())
        .offset(offset)
        .limit(page_size)
    ).all()
    return {
        "data": [
            {
                "id": str(c.id),
                "external_id": c.external_id,
                "email": c.email,
                "first_name": c.first_name,
                "last_name": c.last_name,
                "city": c.city,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in customers
        ]
    }
