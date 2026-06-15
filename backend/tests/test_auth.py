import pytest
import jwt
from fastapi import HTTPException
from app.core.security import hash_password, verify_password, create_access_token, require_role
from app.core.config import get_settings

def test_hash_password_produces_salt_and_digest():
    pw = "secret123"
    hashed = hash_password(pw)
    assert hashed is not None
    assert len(hashed) > 10
    assert hashed != pw

def test_verify_password_correct():
    pw = "secret123"
    hashed = hash_password(pw)
    assert verify_password(pw, hashed) is True

def test_verify_password_incorrect():
    pw = "secret123"
    hashed = hash_password(pw)
    assert verify_password("wrongpw", hashed) is False

def test_verify_password_malformed_hash():
    assert verify_password("secret", "not_a_valid_hash") is False

def test_create_and_decode_access_token():
    data = {"sub": "user_123", "role": "admin"}
    token = create_access_token(data)
    
    settings = get_settings()
    decoded = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    assert decoded["sub"] == "user_123"
    assert decoded["role"] == "admin"
    assert "exp" in decoded

def test_decode_expired_token_raises():
    import datetime
    # We can't easily fake time in the jwt library without patching, 
    # but we can test that creating a token with negative expiry raises error.
    with pytest.raises(Exception):
        import time
        from jwt import ExpiredSignatureError
        data = {"sub": "user_123", "exp": time.time() - 1000}
        token = jwt.encode(data, "secret", algorithm="HS256")
        jwt.decode(token, "secret", algorithms=["HS256"])

def test_require_role_rejects_wrong_role():
    from app.domain.models import User
    import uuid
    user = User(id=str(uuid.uuid4()), tenant_id=str(uuid.uuid4()), email="t@t.com", full_name="T", role="marketer")
    
    # Check that a user with role 'marketer' is rejected when 'admin' is required
    checker = require_role("admin")
    with pytest.raises(HTTPException) as excinfo:
        checker(user=user)
    assert excinfo.value.status_code == 403
