import pytest
from app.domain.models import Campaign, Message
from app.services.campaigns import CampaignService
import uuid

def test_campaign_model_has_scheduled_at():
    camp = Campaign(
        id=str(uuid.uuid4()),
        tenant_id=str(uuid.uuid4()),
        name="Test",
        goal="Test Goal",
        status="draft"
    )
    assert hasattr(camp, "scheduled_at")
    assert camp.scheduled_at is None

def test_campaign_status_values():
    camp = Campaign(status="running")
    assert camp.status == "running"
    
def test_message_default_status_queued():
    msg = Message(
        id=str(uuid.uuid4()),
        tenant_id=str(uuid.uuid4()),
        campaign_id=str(uuid.uuid4()),
        customer_id=str(uuid.uuid4()),
        channel="email",
        variant_key="var1"
    )
    assert msg.status == "queued"
    assert msg.attempts == 0
    assert msg.last_error is None

def test_campaign_service_methods_exist():
    assert hasattr(CampaignService, "draft_from_goal")
    assert hasattr(CampaignService, "launch")
    assert hasattr(CampaignService, "_send_to_provider")
