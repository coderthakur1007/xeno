# Architecture

## System View

```mermaid
flowchart LR
  Marketer[Marketer] --> Web[Next.js Web App]
  Web --> API[FastAPI CRM API]
  API --> PG[(PostgreSQL)]
  API --> Redis[(Redis Cache and Queues)]
  API --> Agents[Multi-agent Copilot]
  Agents --> API
  API --> Simulator[Channel Simulator]
  Simulator --> API
  API --> Metrics[Prometheus Metrics]
  Web --> JWT{JWT Auth}
  JWT --> API
```

## Bounded Contexts

- Identity and access: tenants, users, roles, permissions.
- Customer data platform: customer, order, transaction, consent, attributes.
- Segmentation: visual filters, natural-language intent, SQL-safe compiler, audience estimates.
- Campaign orchestration: drafts, variants, channel plans, launches, provider delivery state.
- Channel simulation: provider receipts, delayed events, failures, retry behavior, dead letters.
- Analytics: funnels, RFM, attribution, CLV-ready facts, churn/model registry surfaces.
- AI copilot: segmentation, strategy, content, channel optimization, analytics, customer intelligence, autonomous execution.
- Admin configuration: prompt templates, feature flags, tenant settings, editable rules.

## Clean Architecture

The FastAPI service separates concerns by package:

- `domain`: SQLAlchemy entities that express business concepts.
- `infrastructure`: repositories and persistence adapters.
- `services`: application use cases such as segmentation and campaign launch.
- `agents`: marketing copilot orchestration.
- `interfaces`: HTTP schemas and FastAPI routes.

External systems are isolated behind adapters. The campaign service sends messages to the simulator over HTTP and receives provider state through versioned webhooks.

## AI-Native Flow

```mermaid
sequenceDiagram
  participant M as Marketer
  participant W as Web
  participant A as CRM API
  participant G as Copilot Graph
  participant S as Simulator
  participant D as Database

  M->>W: Business goal
  W->>A: POST /copilot/plan
  A->>G: Run agents
  G->>D: Read live customer/order/event data
  G-->>A: Segment, strategy, content, channel recommendations
  W->>A: Draft and launch
  A->>D: Persist campaign/messages
  A->>S: Send provider messages
  S-->>A: Async webhook events
  A->>D: Update communication states and analytics facts
```

## Safe Segmentation

The segment compiler maps visual rules and natural language into a constrained SQL grammar. Only whitelisted fields and operators are accepted, every dynamic value is parameter bound, and every query is tenant scoped.

## Authentication Flow

```mermaid
sequenceDiagram
  participant C as Client
  participant A as API
  participant DB as Database

  C->>A: POST /auth/login (email, password)
  A->>DB: Lookup user by email
  DB-->>A: User record with password_hash
  A->>A: Verify password hash
  A-->>C: JWT access_token (exp=1h)
  C->>A: GET /campaigns (Authorization: Bearer token)
  A->>A: Decode JWT, extract tenant_id and role
  A->>A: RBAC permission check
  A->>DB: Query scoped to tenant
  DB-->>A: Results
  A-->>C: 200 OK with data
```

JWT tokens carry the tenant ID and user role. The middleware extracts claims on every request and enforces RBAC before the route handler executes.

## Event Processing

```mermaid
sequenceDiagram
  participant API as CRM API
  participant SIM as Channel Simulator
  participant Redis as Redis
  participant DB as Database

  API->>SIM: POST /provider/messages (batch)
  SIM->>SIM: Rate limit check
  SIM->>SIM: Simulate lifecycle (delay, failure, open, click, convert)
  SIM->>Redis: Store event (fallback: in-memory)
  SIM->>SIM: HMAC sign payload
  SIM->>API: POST /webhooks/channel-events (X-Webhook-Signature)
  API->>API: Verify HMAC signature
  API->>DB: Upsert communication_event
  API->>DB: Update campaign analytics
```

The current local implementation uses async FastAPI background tasks in the simulator and transactional webhook ingestion in the CRM API. Redis is included for production queueing and cache expansion. A production deployment can route `messages.queued`, `provider.receipt`, and `campaign.optimization` events through Redis streams, Celery, Kafka, or a managed queue without changing domain models.

## Entity Relationship Diagram

```mermaid
erDiagram
    tenants ||--o{ users : has
    tenants ||--o{ customers : has
    tenants ||--o{ campaigns : has
    tenants ||--o{ segments : has
    tenants ||--o{ admin_settings : has
    tenants ||--o{ feature_flags : has
    tenants ||--o{ prompt_templates : has
    tenants ||--o{ model_registry : has
    tenants ||--o{ audit_logs : has

    users ||--o{ campaigns : creates
    users ||--o{ audit_logs : generates

    customers ||--o{ orders : places
    customers ||--o{ communication_events : receives

    orders ||--o{ transactions : has

    campaigns ||--o{ campaign_messages : sends
    campaigns ||--o{ communication_events : tracks

    segments ||--o{ campaigns : targets

    tenants {
        uuid id PK
        string name
        string plan
        timestamp created_at
    }
    users {
        uuid id PK
        uuid tenant_id FK
        string email UK
        string password_hash
        string full_name
        string role
        timestamp created_at
    }
    customers {
        uuid id PK
        uuid tenant_id FK
        string external_id
        string email
        string phone
        string first_name
        string last_name
        string city
        string state
        string country
        string gender
        jsonb consent
        jsonb attributes
        timestamp created_at
    }
    orders {
        uuid id PK
        uuid tenant_id FK
        uuid customer_id FK
        string external_id
        string status
        decimal total_amount
        string channel
        jsonb items
        timestamp ordered_at
    }
    transactions {
        uuid id PK
        uuid tenant_id FK
        uuid order_id FK
        decimal amount
        string type
        string status
        timestamp created_at
    }
    campaigns {
        uuid id PK
        uuid tenant_id FK
        string name
        string goal
        string status
        text_arr channels
        jsonb strategy
        jsonb variants
        uuid created_by FK
        timestamp launched_at
        timestamp created_at
    }
    campaign_messages {
        uuid id PK
        uuid tenant_id FK
        uuid campaign_id FK
        uuid customer_id FK
        string channel
        string status
        string provider_message_id
        jsonb content
        timestamp sent_at
    }
    segments {
        uuid id PK
        uuid tenant_id FK
        string name
        string source
        integer estimated_audience
        text sql_query
        jsonb filters
        timestamp created_at
    }
    communication_events {
        uuid id PK
        uuid tenant_id FK
        uuid customer_id FK
        uuid campaign_id FK
        uuid message_id FK
        string channel
        string event_type
        string provider_event_id
        jsonb metadata
        timestamp occurred_at
    }
    admin_settings {
        uuid id PK
        uuid tenant_id FK
        string key UK
        jsonb value
        timestamp updated_at
    }
    feature_flags {
        uuid id PK
        uuid tenant_id FK
        string key UK
        boolean enabled
        jsonb config
    }
    prompt_templates {
        uuid id PK
        uuid tenant_id FK
        string name
        integer version
        text template
        jsonb variables
    }
    model_registry {
        uuid id PK
        uuid tenant_id FK
        string model_name
        string version
        string status
        jsonb metrics
        jsonb feature_set
        string artifact_uri
    }
    audit_logs {
        uuid id PK
        uuid tenant_id FK
        uuid user_id FK
        string action
        string resource
        jsonb detail
        timestamp created_at
    }
```

## Component Interaction — Agent Pipeline

```mermaid
flowchart TD
    subgraph Copilot["Multi-Agent Copilot"]
        Planner[Planner Agent] --> Segmenter[Segmentation Agent]
        Segmenter --> Strategist[Strategy Agent]
        Strategist --> ContentGen[Content Agent]
        ContentGen --> ChannelOpt[Channel Optimizer]
        ChannelOpt --> Executor[Execution Agent]
    end

    Goal["Marketer Goal"] --> Planner
    Segmenter --> DB[(Database)]
    DB --> Segmenter
    Executor --> CampaignSvc[Campaign Service]
    CampaignSvc --> Simulator[Channel Simulator]
    Simulator --> Webhooks[Webhook Ingestion]
    Webhooks --> DB
```

## Campaign Lifecycle Data Flow

```mermaid
flowchart LR
    subgraph Create
        Goal[Business Goal] --> Plan[Copilot Plan]
        Plan --> Segment[Build Segment]
        Segment --> Draft[Campaign Draft]
    end

    subgraph Launch
        Draft --> Messages[Generate Messages]
        Messages --> Simulator[Channel Simulator]
    end

    subgraph Track
        Simulator --> Delivered[Delivered]
        Simulator --> Failed[Failed / Dead Letter]
        Delivered --> Opened[Opened / Read]
        Opened --> Clicked[Clicked]
        Clicked --> Converted[Converted]
    end

    subgraph Analyze
        Converted --> Funnel[Funnel Analytics]
        Funnel --> RFM[RFM Update]
        RFM --> ModelReg[Model Registry]
    end
```

## ML Readiness

The schema includes a `model_registry` table and facts needed for feature generation:

- RFM features from orders.
- Channel affinity from communication events.
- Conversion labels from campaign interactions.
- Customer attributes and consent state.
- Campaign strategy and variant metadata.

Experiment tracking, model versioning, and feature store integration can be added by connecting the model registry to MLflow, Feast, or a managed model registry.
