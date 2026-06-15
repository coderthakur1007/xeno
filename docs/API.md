# API Summary

Base URL: `http://localhost:8000/api/v1`

## Authentication

All endpoints (except `/auth/login`, `/auth/register`, and `/webhooks/channel-events`) require a JWT bearer token.

### POST /auth/login

Authenticate and obtain a JWT token.

**Request:**

```json
{
  "email": "demo@xeno.ai",
  "password": "demo1234"
}
```

**Response (200):**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "demo@xeno.ai",
    "full_name": "Demo User",
    "role": "admin"
  }
}
```

### POST /auth/register

Register a new user account.

**Request:**

```json
{
  "email": "marketer@brand.com",
  "password": "securePass123",
  "full_name": "Campaign Manager",
  "role": "marketer"
}
```

**Response (201):**

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440001",
  "email": "marketer@brand.com",
  "full_name": "Campaign Manager",
  "role": "marketer"
}
```

## Core Endpoints

### GET /analytics/overview

Customer, order, revenue, campaign counts.

**Response (200):**

```json
{
  "total_customers": 25000,
  "total_orders": 90000,
  "total_revenue": 45230000.50,
  "active_campaigns": 3,
  "delivery_rate": 0.96,
  "open_rate": 0.52,
  "conversion_rate": 0.035
}
```

### GET /analytics/rfm

Top RFM customer intelligence rows.

**Parameters:**

| Name      | In    | Type    | Default | Description       |
|-----------|-------|---------|---------|-------------------|
| page      | query | integer | 1       | Page number       |
| page_size | query | integer | 50      | Items per page    |

**Response (200):**

```json
{
  "data": [
    {
      "customer_id": "uuid",
      "email": "user@example.com",
      "recency_days": 5,
      "frequency": 12,
      "monetary": 42500.00,
      "rfm_score": "555",
      "segment": "champion"
    }
  ],
  "page": 1,
  "page_size": 50,
  "total": 25000
}
```

### GET /analytics/cohorts

Monthly acquisition cohort retention matrix.

**Response (200):**

```json
{
  "data": [
    {
      "cohort_month": "2026-01",
      "total_customers": 3200,
      "retention": { "month_1": 0.68, "month_2": 0.45, "month_3": 0.32 }
    }
  ]
}
```

### GET /analytics/customer-health

Customer LTV and churn-risk estimates.

**Parameters:**

| Name      | In    | Type    | Default | Description       |
|-----------|-------|---------|---------|-------------------|
| page      | query | integer | 1       | Page number       |
| page_size | query | integer | 50      | Items per page    |

**Response (200):**

```json
{
  "data": [
    { "customer_id": "uuid", "ltv": 12500.00, "churn_risk": 0.23, "health_score": "healthy" }
  ],
  "page": 1,
  "page_size": 50,
  "total": 25000
}
```

### POST /ingest/customers

JSON ingestion for customer records.

**Request:** Array of customer objects.

**Response (200):**

```json
{ "inserted": 500, "updated": 12, "errors": 0, "message": "OK" }
```

### POST /ingest/customers/csv

CSV customer ingestion via file upload.

### POST /ingest/orders

Ingest order rows.

**Request:**

```json
{
  "rows": [
    {
      "external_id": "ORD-0001",
      "customer_external_id": "CUST-0001",
      "status": "paid",
      "total_amount": 1299.00,
      "channel": "online",
      "items": [{ "sku": "SKU-1234", "category": "skincare", "qty": 1, "price": 1299.00 }],
      "ordered_at": "2026-06-01T12:00:00Z"
    }
  ]
}
```

### POST /ingest/transactions

Ingest transaction rows.

**Request:**

```json
{
  "rows": [
    {
      "order_external_id": "ORD-0001",
      "amount": 1299.00,
      "type": "payment",
      "status": "completed"
    }
  ]
}
```

### POST /ingest/communication-events

Ingest communication event rows.

### POST /segments

Create a visual or natural-language audience.

**Request:**

```json
{
  "name": "High-LTV inactive 90d",
  "source": "natural_language",
  "query": "customers who spent over 5000 and haven't ordered in 90 days"
}
```

**Response (200):**

```json
{
  "id": "uuid",
  "name": "High-LTV inactive 90d",
  "source": "natural_language",
  "estimated_audience": 3450,
  "sql": "SELECT ... WHERE ...",
  "created_at": "2026-06-15T00:00:00Z"
}
```

### GET /segments

List recent segments.

**Parameters:**

| Name      | In    | Type    | Default | Description       |
|-----------|-------|---------|---------|-------------------|
| page      | query | integer | 1       | Page number       |
| page_size | query | integer | 50      | Items per page    |

### POST /copilot/plan

Run the multi-agent marketing planner.

**Request:**

```json
{
  "goal": "Increase repeat purchases from customers inactive for 90 days",
  "name": "Reactivation Q2"
}
```

**Response (200):**

```json
{
  "campaign_id": "uuid",
  "segment": { "name": "Inactive 90d", "estimated_audience": 4200, "sql": "..." },
  "strategy": { "conversion_probability": 0.043 },
  "variants": [{ "key": "variant_1" }, { "key": "variant_2" }],
  "channels": ["whatsapp", "email"],
  "explanation": "Targeting customers who last purchased 90+ days ago..."
}
```

### GET /copilot/proof

Run a broad prompt matrix and return generated intents, safe SQL, channel decisions, and forecasts.

### GET /reports/copilot-proof.xlsx

Download an Excel workbook proving prompt coverage and training-signal mapping.

### POST /campaigns/from-goal

Create a campaign draft from a business goal.

### GET /campaigns

List campaigns.

**Parameters:**

| Name      | In    | Type    | Default | Description       |
|-----------|-------|---------|---------|-------------------|
| page      | query | integer | 1       | Page number       |
| page_size | query | integer | 50      | Items per page    |

### POST /campaigns/{campaign_id}/launch

Send campaign messages through the simulator.

**Response (200):**

```json
{
  "campaign_id": "uuid",
  "messages_sent": 4200,
  "status": "running"
}
```

### GET /campaigns/{campaign_id}/funnel

Campaign delivery funnel with stage counts.

**Response (200):**

```json
{
  "campaign_id": "uuid",
  "stages": [
    { "stage": "sent", "count": 4200, "percentage": 100.0 },
    { "stage": "delivered", "count": 4032, "percentage": 96.0 },
    { "stage": "opened", "count": 2100, "percentage": 50.0 },
    { "stage": "clicked", "count": 630, "percentage": 15.0 },
    { "stage": "converted", "count": 168, "percentage": 4.0 }
  ]
}
```

### POST /webhooks/channel-events

Provider callback ingestion. No auth required — verified by `X-Webhook-Signature` header.

### GET /admin/settings

Tenant settings (admin only).

### PUT /admin/settings/{key}

Upsert a tenant setting (admin only).

**Request:**

```json
{ "value": { "max_per_customer_per_week": 5, "quiet_hours": ["22:00", "08:00"] } }
```

### GET /admin/feature-flags

Feature flags for the tenant (admin only).

### GET /audit-logs

Latest audit records (admin only).

**Parameters:**

| Name      | In    | Type    | Default | Description       |
|-----------|-------|---------|---------|-------------------|
| page      | query | integer | 1       | Page number       |
| page_size | query | integer | 50      | Items per page    |

## Tenant Context

Requests can pass `X-Tenant-Id`. If omitted, the API creates or uses a default demo tenant.

## Access Control

The demo user defaults to `admin`. Permissions are enforced by role:

- `admin`: read, write, launch, admin.
- `marketer`: read, write, launch.
- `analyst`: read.
- `viewer`: read.

## Pagination

All list endpoints support pagination with `page` and `page_size` query parameters. Responses include `page`, `page_size`, and `total` fields.

Default page size is 50. Maximum page size is 200.

## Error Codes

| Status | Meaning                      | Example                                                  |
|--------|------------------------------|----------------------------------------------------------|
| 400    | Bad Request / Validation     | `{ "detail": [{ "loc": ["body", "goal"], "msg": "field required" }] }` |
| 401    | Unauthorized                 | `{ "detail": "Missing or invalid token", "status_code": 401 }` |
| 403    | Forbidden                    | `{ "detail": "Insufficient permissions", "status_code": 403 }` |
| 404    | Not Found                    | `{ "detail": "Campaign not found", "status_code": 404 }` |
| 429    | Rate Limited                 | `{ "detail": "Rate limit exceeded" }` |
| 500    | Internal Server Error        | `{ "detail": "Internal error", "status_code": 500 }` |

## Rate Limiting

API rate limits:

- **General**: 1000 requests per minute per tenant.
- **Ingestion**: 100 requests per minute per tenant.
- **Copilot**: 30 requests per minute per tenant.
- **Simulator**: 100 messages per second (in-memory counter).

Exceeding limits returns `429 Too Many Requests`.

## Webhook Signature Verification

The channel simulator signs every webhook event with HMAC-SHA256.

**Verification steps:**

1. Read the raw request body bytes.
2. Compute `hmac.new(WEBHOOK_SECRET.encode(), body, sha256).hexdigest()`.
3. Compare the result with the `X-Webhook-Signature` header.
4. Reject the event if signatures do not match.

The secret is configured via the `WEBHOOK_SECRET` environment variable (default: `webhook-secret-change-me`).

## Observability

- `GET /healthz`
- `GET /metrics`
