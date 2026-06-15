"""Fix demo user password hash to use the proper format expected by security.py"""
import sys
import os

# Ensure the API app is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "apps", "api"))

from sqlalchemy import create_engine, text
from app.core.config import get_settings
from app.core.security import hash_password

engine = create_engine(get_settings().database_url, connect_args={"check_same_thread": False})
with engine.begin() as conn:
    new_hash = hash_password("demo1234")
    conn.execute(
        text("UPDATE users SET password_hash = :pw WHERE email = :email"),
        {"pw": new_hash, "email": "demo@xeno.ai"},
    )
    print(f"Updated demo@xeno.ai password hash to proper format")
    print(f"New hash format: {new_hash[:20]}...")
