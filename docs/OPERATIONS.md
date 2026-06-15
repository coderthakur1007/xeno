# Operations

## Local Deployment

```bash
docker compose up --build
```

Seed at scale:

```bash
docker compose exec api python scripts/seed.py --customers 25000 --orders 90000 --events 160000
```

## Production Checklist

- Replace `JWT_SECRET` and database credentials.
- Put API, simulator, and web behind TLS.
- Restrict CORS origins.
- Configure real object storage for CSV uploads and model artifacts.
- Route event processing through Redis streams, Kafka, SQS, or a managed queue.
- Add managed PostgreSQL backups and point-in-time recovery.
- Export Prometheus metrics to Grafana, Datadog, or OpenTelemetry collector.
- Configure CI secrets for deployment environments.
- Use provider-specific adapters for WhatsApp, SMS, Email, and RCS in place of the simulator.

## CI/CD

The included GitHub Actions workflow installs Python and Node dependencies, runs backend and simulator tests, type-checks/builds the web app, and leaves deployment as an environment-specific step.
