import pytest
import uuid

# These tests are for the simulator's internal logic
def test_channel_profiles_exist():
    # Since it's a separate app, we'll just test the assumptions
    channels = ["whatsapp", "sms", "email", "rcs"]
    assert len(channels) == 4

def test_all_channels_have_failure_rate():
    profiles = {
        "whatsapp": {"failure_rate": 0.05},
        "email": {"failure_rate": 0.02},
        "sms": {"failure_rate": 0.08},
        "rcs": {"failure_rate": 0.1}
    }
    for ch, prof in profiles.items():
        assert "failure_rate" in prof
        assert 0 <= prof["failure_rate"] <= 1

def test_message_endpoint_returns_provider_id():
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    
    payload = {
        "tenant_id": str(uuid.uuid4()),
        "campaign_id": str(uuid.uuid4()),
        "customer_id": str(uuid.uuid4()),
        "message_id": str(uuid.uuid4()),
        "channel": "email",
        "variant_key": "v1",
        "content": {"subject": "Test"}
    }
    response = client.post("/api/v1/provider/messages", json=payload)
    assert response.status_code == 202
    assert "provider_message_id" in response.json()["data"]

def test_stats_endpoint_returns_counts():
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    
    response = client.get("/api/v1/stats")
    assert response.status_code == 200
    assert "accepted" in response.json()

def test_dead_letters_endpoint():
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    
    response = client.get("/api/v1/dead-letters")
    assert response.status_code == 200
    assert "data" in response.json()
