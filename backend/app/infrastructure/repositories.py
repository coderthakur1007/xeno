"""Infrastructure-layer repository classes.

Each repository wraps SQLAlchemy queries for a single aggregate or
read-model.  All writes go through the ORM; heavy reads may use raw SQL
for performance (e.g. analytics, bulk upserts).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Select, func, select, text, update
from sqlalchemy.orm import Session

from app.domain.models import (
    AdminSetting,
    AuditLog,
    Campaign,
    CommunicationEvent,
    Customer,
    FeatureFlag,
    Message,
    Order,
    PromptTemplate,
    Segment,
    Tenant,
    Transaction,
    User,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BULK_BATCH_SIZE = 1000


def _try_cache_get(key: str) -> Any | None:
    """Attempt to read from the Redis cache; return None on any failure."""
    try:
        from app.core.redis_client import CacheService
        return CacheService().get(key)
    except Exception:
        return None


def _try_cache_set(key: str, value: Any, ttl: int = 300) -> None:
    """Attempt to write to the Redis cache; silently swallow errors."""
    try:
        from app.core.redis_client import CacheService
        CacheService().set(key, value, ttl=ttl)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# TenantRepository
# ---------------------------------------------------------------------------


class TenantRepository:
    def __init__(self, db: Session):
        self.db = db

    def default_tenant(self) -> Tenant:
        tenant = self.db.scalar(select(Tenant).limit(1))
        if tenant:
            return tenant
        tenant = Tenant(name="Xeno Demo Retail")
        self.db.add(tenant)
        self.db.flush()
        user = User(tenant_id=tenant.id, email="admin@xeno.local", full_name="Demo Admin", role="admin")
        self.db.add(user)
        self.db.commit()
        return tenant

    def default_user(self, tenant_id: uuid.UUID) -> User:
        return self.db.scalar(select(User).where(User.tenant_id == tenant_id).limit(1))


# ---------------------------------------------------------------------------
# CustomerRepository
# ---------------------------------------------------------------------------


class CustomerRepository:
    def __init__(self, db: Session):
        self.db = db

    def upsert_many(self, tenant_id: uuid.UUID, rows: list[dict[str, Any]]) -> int:
        """Bulk upsert customers using INSERT … ON CONFLICT DO UPDATE.

        Rows are processed in batches of ``_BULK_BATCH_SIZE`` (1000).
        Each row **must** contain an ``external_id`` key.

        Returns:
            Total number of rows upserted.
        """
        if not rows:
            return 0

        # Determine the full set of columns present across all rows
        all_keys: set[str] = set()
        for row in rows:
            all_keys.update(row.keys())
        # external_id is the natural key used for conflict detection
        all_keys.discard("external_id")
        update_cols = sorted(all_keys)

        count = 0
        for batch_start in range(0, len(rows), _BULK_BATCH_SIZE):
            batch = rows[batch_start : batch_start + _BULK_BATCH_SIZE]

            # Build per-row value lists
            values_fragments: list[str] = []
            params: dict[str, Any] = {"tenant_id": str(tenant_id)}
            for idx, row in enumerate(batch):
                placeholders = [f":tenant_id", f":eid_{idx}"]
                params[f"eid_{idx}"] = row["external_id"]
                for col in update_cols:
                    param_name = f"{col}_{idx}"
                    placeholders.append(f":{param_name}")
                    value = row.get(col)
                    # Serialise dicts/lists to JSON strings for JSON columns
                    if isinstance(value, (dict, list)):
                        value = json.dumps(value)
                    params[param_name] = value
                values_fragments.append(f"({', '.join(placeholders)})")

            columns_list = ", ".join(["tenant_id", "external_id"] + update_cols)
            values_sql = ", ".join(values_fragments)

            # Build the SET clause for ON CONFLICT
            set_clauses = [f"{col} = EXCLUDED.{col}" for col in update_cols]
            set_clauses.append("updated_at = now()")
            set_sql = ", ".join(set_clauses)

            stmt = text(
                f"INSERT INTO customers ({columns_list}) "
                f"VALUES {values_sql} "
                f"ON CONFLICT (tenant_id, external_id) DO UPDATE SET {set_sql}"
            )
            self.db.execute(stmt, params)
            count += len(batch)

        self.db.commit()
        return count

    def list_by_segment_sql(self, sql_text: str, params: dict[str, Any], limit: int = 5000) -> list[Customer]:
        stmt = text(f"SELECT c.* FROM customers c WHERE c.id IN ({sql_text}) LIMIT :limit")
        return list(self.db.execute(stmt, {**params, "limit": limit}).mappings())


# ---------------------------------------------------------------------------
# IngestionRepository
# ---------------------------------------------------------------------------


class IngestionRepository:
    def __init__(self, db: Session):
        self.db = db

    def upsert_orders(self, tenant_id: uuid.UUID, rows: list[dict[str, Any]]) -> int:
        count = 0
        for row in rows:
            existing = self.db.scalar(select(Order).where(Order.tenant_id == tenant_id, Order.external_id == row["external_id"]))
            if existing:
                for key, value in row.items():
                    setattr(existing, key, value)
            else:
                self.db.add(Order(tenant_id=tenant_id, **row))
            count += 1
        self.db.commit()
        return count

    def add_transactions(self, tenant_id: uuid.UUID, rows: list[dict[str, Any]]) -> int:
        for row in rows:
            self.db.add(Transaction(tenant_id=tenant_id, **row))
        self.db.commit()
        return len(rows)

    def add_events(self, tenant_id: uuid.UUID, rows: list[dict[str, Any]]) -> int:
        for row in rows:
            self.db.add(CommunicationEvent(tenant_id=tenant_id, metadata_=row.pop("metadata", {}), **row))
        self.db.commit()
        return len(rows)


# ---------------------------------------------------------------------------
# SegmentRepository
# ---------------------------------------------------------------------------


class SegmentRepository:
    def __init__(self, db: Session):
        self.db = db

    def count(self, sql_text: str, params: dict[str, Any]) -> int:
        return int(self.db.execute(text(f"SELECT count(*) FROM ({sql_text}) audience"), params).scalar_one())

    def create(self, segment: Segment) -> Segment:
        self.db.add(segment)
        self.db.commit()
        self.db.refresh(segment)
        return segment

    def get(self, segment_id: uuid.UUID) -> Segment | None:
        return self.db.get(Segment, segment_id)

    def recent(
        self,
        tenant_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Segment]:
        """Return recent segments for *tenant_id* with pagination."""
        return list(
            self.db.scalars(
                select(Segment)
                .where(Segment.tenant_id == tenant_id)
                .order_by(Segment.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
        )


# ---------------------------------------------------------------------------
# CampaignRepository
# ---------------------------------------------------------------------------


class CampaignRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, campaign: Campaign) -> Campaign:
        self.db.add(campaign)
        self.db.commit()
        self.db.refresh(campaign)
        return campaign

    def get(self, campaign_id: uuid.UUID) -> Campaign | None:
        return self.db.get(Campaign, campaign_id)

    def list(
        self,
        tenant_id: uuid.UUID,
        limit: int = 25,
        offset: int = 0,
    ) -> list[Campaign]:
        """Return campaigns for *tenant_id* with pagination."""
        return list(
            self.db.scalars(
                select(Campaign)
                .where(Campaign.tenant_id == tenant_id)
                .order_by(Campaign.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
        )

    def mark_running(self, campaign_id: uuid.UUID) -> None:
        self.db.execute(update(Campaign).where(Campaign.id == campaign_id).values(status="running", launched_at=datetime.now(timezone.utc)))
        self.db.commit()

    def add_message(self, message: Message) -> Message:
        self.db.add(message)
        self.db.flush()
        return message

    def pending_messages(self, campaign_id: uuid.UUID, limit: int = 500) -> list[Message]:
        return list(self.db.scalars(select(Message).where(Message.campaign_id == campaign_id, Message.status == "queued").limit(limit)))


# ---------------------------------------------------------------------------
# AnalyticsRepository
# ---------------------------------------------------------------------------


class AnalyticsRepository:
    def __init__(self, db: Session):
        self.db = db

    def overview(self, tenant_id: uuid.UUID) -> dict[str, Any]:
        """Return high-level tenant metrics, cached in Redis for 60 s."""
        cache_key = f"analytics:overview:{tenant_id}"
        cached = _try_cache_get(cache_key)
        if cached is not None:
            return cached

        customers = self.db.scalar(select(func.count(Customer.id)).where(Customer.tenant_id == tenant_id)) or 0
        orders = self.db.scalar(select(func.count(Order.id)).where(Order.tenant_id == tenant_id)) or 0
        revenue = self.db.scalar(select(func.coalesce(func.sum(Order.total_amount), 0)).where(Order.tenant_id == tenant_id, Order.status == "paid")) or 0
        campaigns = self.db.scalar(select(func.count(Campaign.id)).where(Campaign.tenant_id == tenant_id)) or 0
        result = {"customers": customers, "orders": orders, "revenue": float(revenue), "campaigns": campaigns}

        _try_cache_set(cache_key, result, ttl=60)
        return result

    def funnel(self, campaign_id: uuid.UUID) -> dict[str, int]:
        rows = self.db.execute(
            select(CommunicationEvent.event_type, func.count(CommunicationEvent.id)).where(CommunicationEvent.campaign_id == campaign_id).group_by(CommunicationEvent.event_type)
        ).all()
        return {event_type: count for event_type, count in rows}

    def rfm(self, tenant_id: uuid.UUID) -> list[dict[str, Any]]:
        query = text(
            """
            SELECT c.id, c.first_name, c.email,
              EXTRACT(days FROM now() - max(o.ordered_at))::int AS recency_days,
              count(o.id)::int AS frequency,
              coalesce(sum(o.total_amount),0)::float AS monetary
            FROM customers c
            LEFT JOIN orders o ON o.customer_id = c.id AND o.status = 'paid'
            WHERE c.tenant_id = :tenant_id
            GROUP BY c.id
            ORDER BY monetary DESC
            LIMIT 50
            """
        )
        return [dict(row) for row in self.db.execute(query, {"tenant_id": tenant_id}).mappings()]

    def cohorts(self, tenant_id: uuid.UUID) -> list[dict[str, Any]]:
        query = text(
            """
            WITH first_orders AS (
              SELECT customer_id, date_trunc('month', min(ordered_at)) cohort_month
              FROM orders WHERE tenant_id = :tenant_id AND status='paid' GROUP BY customer_id
            )
            SELECT cohort_month::date,
              count(*)::int customers,
              count(*) FILTER (WHERE EXISTS (
                SELECT 1 FROM orders o WHERE o.customer_id = f.customer_id
                AND o.ordered_at >= f.cohort_month + interval '30 days'
              ))::int retained_30d
            FROM first_orders f
            GROUP BY cohort_month
            ORDER BY cohort_month DESC
            LIMIT 12
            """
        )
        return [dict(row) for row in self.db.execute(query, {"tenant_id": tenant_id}).mappings()]

    def customer_health(self, tenant_id: uuid.UUID) -> list[dict[str, Any]]:
        query = text(
            """
            SELECT c.id, c.first_name, c.email,
              coalesce(sum(o.total_amount),0)::float AS estimated_ltv,
              count(o.id)::int AS orders,
              EXTRACT(days FROM now() - max(o.ordered_at))::int AS recency_days,
              least(0.95, greatest(0.02, coalesce(EXTRACT(days FROM now() - max(o.ordered_at)), 180) / 240.0))::float AS churn_probability
            FROM customers c
            LEFT JOIN orders o ON o.customer_id = c.id AND o.status='paid'
            WHERE c.tenant_id = :tenant_id
            GROUP BY c.id
            ORDER BY churn_probability DESC, estimated_ltv DESC
            LIMIT 100
            """
        )
        return [dict(row) for row in self.db.execute(query, {"tenant_id": tenant_id}).mappings()]


# ---------------------------------------------------------------------------
# EventRepository
# ---------------------------------------------------------------------------


class EventRepository:
    def __init__(self, db: Session):
        self.db = db

    def record(self, event: CommunicationEvent) -> CommunicationEvent:
        self.db.add(event)
        if event.message_id:
            status = {
                "delivered": "delivered",
                "failed": "failed",
                "opened": "opened",
                "clicked": "clicked",
                "read": "read",
                "converted": "converted",
            }.get(event.event_type)
            if status:
                self.db.execute(update(Message).where(Message.id == event.message_id).values(status=status, updated_at=datetime.now(timezone.utc)))
        self.db.commit()
        return event


# ---------------------------------------------------------------------------
# AuditRepository
# ---------------------------------------------------------------------------


class AuditRepository:
    def __init__(self, db: Session):
        self.db = db

    def log(self, **kwargs: Any) -> None:
        self.db.add(AuditLog(**kwargs))
        self.db.commit()

    def recent(
        self,
        tenant_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditLog]:
        """Return recent audit log entries for *tenant_id* with pagination."""
        return list(
            self.db.scalars(
                select(AuditLog)
                .where(AuditLog.tenant_id == tenant_id)
                .order_by(AuditLog.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
        )


# ---------------------------------------------------------------------------
# FeatureFlagRepository
# ---------------------------------------------------------------------------


class FeatureFlagRepository:
    """Read-only access to per-tenant feature flags."""

    @staticmethod
    def is_enabled(db: Session, tenant_id: uuid.UUID, key: str) -> bool:
        """Return whether the feature flag *key* is enabled for *tenant_id*.

        Returns ``False`` if the flag does not exist.
        """
        flag = db.scalar(
            select(FeatureFlag).where(
                FeatureFlag.tenant_id == tenant_id,
                FeatureFlag.key == key,
            )
        )
        return flag.enabled if flag else False

    @staticmethod
    def get_config(db: Session, tenant_id: uuid.UUID, key: str) -> dict[str, Any]:
        """Return the JSON config dict for flag *key*, or ``{}`` if missing."""
        flag = db.scalar(
            select(FeatureFlag).where(
                FeatureFlag.tenant_id == tenant_id,
                FeatureFlag.key == key,
            )
        )
        return flag.config if flag else {}


# ---------------------------------------------------------------------------
# PromptTemplateRepository
# ---------------------------------------------------------------------------


class PromptTemplateRepository:
    """Read-only access to versioned prompt templates."""

    @staticmethod
    def get_active(
        db: Session,
        tenant_id: uuid.UUID,
        name: str,
    ) -> PromptTemplate | None:
        """Return the active ``PromptTemplate`` with *name* for *tenant_id*.

        If multiple active templates share the same name, the one with the
        highest ``version`` is returned.
        """
        return db.scalar(
            select(PromptTemplate)
            .where(
                PromptTemplate.tenant_id == tenant_id,
                PromptTemplate.name == name,
                PromptTemplate.is_active.is_(True),
            )
            .order_by(PromptTemplate.version.desc())
            .limit(1)
        )


# ---------------------------------------------------------------------------
# AdminSettingRepository
# ---------------------------------------------------------------------------


class AdminSettingRepository:
    """Read-only access to per-tenant admin settings."""

    @staticmethod
    def get_value(
        db: Session,
        tenant_id: uuid.UUID,
        key: str,
    ) -> Any | None:
        """Return the JSON *value* for setting *key*, or ``None`` if missing."""
        setting = db.scalar(
            select(AdminSetting).where(
                AdminSetting.tenant_id == tenant_id,
                AdminSetting.key == key,
            )
        )
        return setting.value if setting else None
