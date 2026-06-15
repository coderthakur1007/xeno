import pytest
import uuid
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_healthz_returns_ok():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "Xeno Channel Simulator"}

def test_provider_messages_accepts_valid_payload():
    payload = {
        "tenant_id": str(uuid.uuid4()),
        "campaign_id": str(uuid.uuid4()),
        "customer_id": str(uuid.uuid4()),
        "message_id": str(uuid.uuid4()),
        "channel": "whatsapp",
        "variant_key": "v1",
        "content": {"body": "Test"}
    }
    response = client.post("/api/v1/provider/messages", json=payload)
    assert response.status_code == 202
    assert response.json()["data"]["status"] == "accepted"

def test_provider_events_returns_list():
    response = client.get("/api/v1/provider/events")
    assert response.status_code == 200
    assert isinstance(response.json()["data"], list)

def test_batch_messages_endpoint():
    payload = {
        "messages": [
            {
                "tenant_id": str(uuid.uuid4()),
                "campaign_id": str(uuid.uuid4()),
                "customer_id": str(uuid.uuid4()),
                "message_id": str(uuid.uuid4()),
                "channel": "email",
                "variant_key": "v1",
                "content": {"body": "Test 1"}
            },
            {
                "tenant_id": str(uuid.uuid4()),
                "campaign_id": str(uuid.uuid4()),
                "customer_id": str(uuid.uuid4()),
                "message_id": str(uuid.uuid4()),
                "channel": "sms",
                "variant_key": "v1",
                "content": {"body": "Test 2"}
            }
        ]
    }
    response = client.post("/api/v1/provider/messages/batch", json=payload)
    assert response.status_code == 202
    assert response.json()["data"]["accepted"] == 2
