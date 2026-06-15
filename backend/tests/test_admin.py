import pytest
import uuid
from app.domain.models import FeatureFlag, AdminSetting, PromptTemplate, ModelRegistry, AuditLog

def test_feature_flag_model_defaults():
    ff = FeatureFlag(
        id=str(uuid.uuid4()),
        tenant_id=str(uuid.uuid4()),
        key="test_flag"
    )
    assert ff.enabled is False
    assert ff.config == {}

def test_admin_setting_model():
    setting = AdminSetting(
        id=str(uuid.uuid4()),
        tenant_id=str(uuid.uuid4()),
        key="test_setting",
        value={"foo": "bar"}
    )
    assert setting.value["foo"] == "bar"

def test_prompt_template_model():
    pt = PromptTemplate(
        id=str(uuid.uuid4()),
        tenant_id=str(uuid.uuid4()),
        name="test_template",
        template="Hello {{name}}"
    )
    assert pt.version == 1
    assert pt.is_active is True
    assert pt.variables == []

def test_model_registry_model():
    mr = ModelRegistry(
        id=str(uuid.uuid4()),
        tenant_id=str(uuid.uuid4()),
        model_name="churn",
        version="v1",
        status="active"
    )
    assert mr.model_name == "churn"
    assert mr.metrics == {}

def test_audit_log_model():
    al = AuditLog(
        id=str(uuid.uuid4()),
        tenant_id=str(uuid.uuid4()),
        action="test_action",
        resource_type="user"
    )
    assert al.action == "test_action"
