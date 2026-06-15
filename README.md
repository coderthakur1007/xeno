# Xeno AI Campaign Copilot

[![CI](https://github.com/xeno-ai/campaign-copilot/actions/workflows/ci.yml/badge.svg)](https://github.com/xeno-ai/campaign-copilot/actions)
[![Coverage](https://img.shields.io/badge/coverage-80%25-green)](.)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Production-grade mini CRM for retail and D2C lifecycle marketing across WhatsApp, SMS, Email, and RCS.

## What Is Included

- Next.js web app with campaign dashboard, visual segment builder, AI copilot, analytics, customer intelligence, and admin settings.
- FastAPI CRM backend with clean architecture, repository pattern, RBAC, audit logs, API versioning, rate limiting, retries, caching, ingestion, segmentation, campaigns, and analytics.
- Channel Simulator microservice that behaves like messaging providers with delayed callbacks, failures, opens, clicks, conversions, retries, and webhook receipts.
- PostgreSQL schema, Redis queues/cache, Docker Compose, seed generator, CI pipeline, OpenAPI contract, and architecture documentation.
- Multi-agent marketing copilot implemented with LangGraph-compatible orchestration primitives and deterministic local fallbacks for offline evaluation.

## Architecture

```mermaid
flowchart LR
  Marketer --> Web[Next.js]
  Web --> API[FastAPI]
  API --> PG[(PostgreSQL)]
  API --> Redis[(Redis)]
  API --> Copilot[AI Agents]
  API --> Sim[Simulator]
  Sim --> API
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/API.md](docs/API.md), and [contracts/openapi.yaml](contracts/openapi.yaml) for full details.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose v2+
- Node.js 22+ (for local web development)
- Python 3.12+ (for local API/simulator development)
- Git

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/xeno-ai/campaign-copilot.git
cd campaign-copilot

# 2. Copy environment template
cp .env.example .env

# 3. Start all services
docker compose up --build
```

Services:

- Web: http://localhost:3000
- API: http://localhost:8000/docs
- Simulator: http://localhost:8100/docs
- Postgres: localhost:5432
- Redis: localhost:6379

## Developer Setup

### Local API development

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
PYTHONPATH=. uvicorn app.main:app --reload --port 8000
```

### Local Web development

```bash
cd apps/web
npm ci
npm run dev
```

### Local Simulator development

```bash
cd apps/simulator
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. uvicorn app.main:app --reload --port 8100
```

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://xeno:xeno@localhost:5432/xeno` |
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379/0` |
| `JWT_SECRET` | Secret for signing JWT tokens | `change-me-in-production` |
| `WEBHOOK_SECRET` | HMAC secret for webhook signatures | `webhook-secret-change-me` |
| `OPENAI_API_KEY` | OpenAI API key for AI copilot | (optional, uses local fallback) |
| `CRM_WEBHOOK_URL` | Callback URL for simulator events | `http://localhost:8000/api/v1/webhooks/channel-events` |
| `SIMULATOR_URL` | Simulator base URL | `http://localhost:8100` |
| `APP_ENV` | Environment name | `development` |
| `LOG_LEVEL` | Logging level | `info` |
| `RATE_LIMIT_PER_SEC` | Simulator rate limit (msgs/sec) | `100` |
| `NEXT_PUBLIC_API_URL` | Public API URL for Next.js frontend | `http://localhost:8000` |

## Seed Data

Generate realistic demo data:

```bash
# Standard seed
docker compose exec api python scripts/seed.py --customers 25000 --orders 90000 --events 160000

# With demo login user (demo@xeno.ai / demo1234)
docker compose exec api python scripts/seed.py --customers 25000 --orders 90000 --events 160000 --demo-user
```

## Testing

```bash
# Run all Python tests
docker compose exec api pytest
docker compose exec simulator pytest

# Run with coverage
PYTHONPATH=apps/api pytest apps/api/tests --cov=app --cov-report=html

# Run web tests
cd apps/web && npm test

# Lint Python code
pip install ruff && ruff check apps/api/app apps/simulator/app

# Lint web code
cd apps/web && npm run lint
```

## API Quick Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/login` | Authenticate, get JWT token |
| POST | `/auth/register` | Register new user |
| POST | `/copilot/plan` | AI campaign planner |
| GET | `/copilot/proof` | Prompt coverage matrix |
| GET | `/reports/copilot-proof.xlsx` | Download proof workbook |
| POST | `/campaigns/from-goal` | Create campaign from goal |
| GET | `/campaigns` | List campaigns |
| POST | `/campaigns/{id}/launch` | Launch campaign |
| GET | `/campaigns/{id}/funnel` | Campaign delivery funnel |
| POST | `/segments` | Create audience segment |
| GET | `/segments` | List segments |
| GET | `/analytics/overview` | Dashboard metrics |
| GET | `/analytics/rfm` | RFM intelligence |
| GET | `/analytics/cohorts` | Cohort retention |
| GET | `/analytics/customer-health` | LTV and churn risk |
| POST | `/ingest/orders` | Ingest orders |
| POST | `/ingest/transactions` | Ingest transactions |
| POST | `/ingest/communication-events` | Ingest comm events |
| POST | `/webhooks/channel-events` | Provider webhook |
| GET | `/admin/settings` | Tenant settings |
| PUT | `/admin/settings/{key}` | Upsert setting |
| GET | `/admin/feature-flags` | Feature flags |
| GET | `/audit-logs` | Audit trail |

## Configuration

### Feature Flags

Feature flags are per-tenant and managed via the admin API:

- `ai_autonomous_execution` — Allow copilot to launch campaigns without confirmation.
- `rcs_experiments` — Enable RCS channel experiments.
- `churn_predictions` — Enable ML-powered churn prediction scores.

### Admin Settings

Key settings that control campaign behavior:

- `frequency_caps` — Max messages per customer per week and quiet hours.
- `attribution` — Attribution model (`last_touch`, `first_touch`, `linear`) and window.
- `channel_budget` — Budget allocation ratios across channels.

## Demo Goals To Try

- "Increase repeat purchases from customers inactive for 90 days"
- "Win back VIP customers who viewed products but did not buy this month"
- "Create a WhatsApp and email A/B campaign for high-LTV skincare buyers"
- "Convert new shoppers into second-purchase customers"
- "Target email customers who clicked but have not converted"
- "Recover customers with failed SMS deliveries"
- "Promote footwear sale to gold tier shoppers in Bangalore"

The copilot plans strategy, builds a safe executable segment, estimates audience size, recommends channels, generates personalized content variants, launches through the simulator, and consumes provider events in real time.

## Proof That More Prompts Work

Run the prompt coverage regression tests:

```bash
PYTHONPATH=apps/api pytest apps/api/tests -q
```

Generate an offline Excel proof workbook:

```bash
python scripts/generate_proof_workbook.py
```

Output:

```text
outputs/xeno_copilot_prompt_proof.xlsx
```

When the API is running, the app also exposes:

- `GET /api/v1/copilot/proof`
- `GET /api/v1/reports/copilot-proof.xlsx`

The workbook includes prompt coverage, detected intents, safe parameterized SQL, forecast outputs, and training-signal rows used by the copilot model design.

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit your changes: `git commit -m 'Add my feature'`
4. Push to the branch: `git push origin feature/my-feature`
5. Open a Pull Request

Please ensure:
- All tests pass (`pytest`, `npm test`)
- Code passes linting (`ruff check`, `npm run lint`)
- New endpoints include OpenAPI schema updates in `contracts/openapi.yaml`
- Database changes include migration scripts

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.
