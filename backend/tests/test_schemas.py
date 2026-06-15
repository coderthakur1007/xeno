import pytest
from pydantic import ValidationError
from app.interfaces.schemas import (
    LoginRequest, 
    RegisterRequest, 
    IngestRowRequest, 
    IngestCustomersRequest, 
    SegmentCreateRequest
)

def test_login_request_valid():
    req = LoginRequest(email="test@xeno.ai", password="password123")
    assert req.email == "test@xeno.ai"
    assert req.password == "password123"

def test_register_request_min_password_length():
    with pytest.raises(ValidationError):
        RegisterRequest(email="test@xeno.ai", full_name="Test", password="short")
        
def test_customer_ingest_row_requires_external_id():
    with pytest.raises(ValidationError):
        # Missing external_id
        IngestRowRequest(email="test@test.com")
        
def test_customer_ingest_row_validates_email():
    with pytest.raises(ValidationError):
        IngestRowRequest(external_id="123", email="not_an_email")

def test_order_ingest_row_validates_amount():
    from app.interfaces.schemas import IngestOrderRowRequest
    with pytest.raises(ValidationError):
        IngestOrderRowRequest(external_id="123", customer_id="1", total_amount=-10, status="completed", ordered_at="2023-01-01T00:00:00Z")

def test_segment_create_request_validates_source():
    with pytest.raises(ValidationError):
        SegmentCreateRequest(name="Seg 1", source="invalid_source", query="test")
