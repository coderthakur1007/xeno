import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.database import Base

# Use SQLite in-memory for tests
TEST_DATABASE_URL = 'sqlite:///:memory:'

@pytest.fixture
def db_engine():
    engine = create_engine(TEST_DATABASE_URL, connect_args={'check_same_thread': False})
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def db_session(db_engine):
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()

@pytest.fixture
def tenant_and_user(db_session):
    # Create a test tenant and user
    import uuid
    from app.domain.models import Tenant, User
    tenant = Tenant(id=str(uuid.uuid4()), name='Test Tenant', plan='enterprise')
    db_session.add(tenant)
    db_session.flush()
    user = User(id=str(uuid.uuid4()), tenant_id=tenant.id, email='test@test.com', full_name='Test User', role='admin', is_active=True)
    db_session.add(user)
    db_session.commit()
    return tenant, user
