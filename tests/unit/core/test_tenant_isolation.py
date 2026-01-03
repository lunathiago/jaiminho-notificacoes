from unittest.mock import AsyncMock, Mock

import pytest

from jaiminho_notificacoes.core.tenant import TenantContext, TenantIsolationMiddleware, TenantResolver
from jaiminho_notificacoes.persistence.models import WAPIInstance


@pytest.fixture
def resolver_stub():
    resolver = TenantResolver.__new__(TenantResolver)
    resolver.instances_repo = Mock()
    resolver._cache = {}
    resolver.rds_client = None
    return resolver


def _make_tenant_context(user_id="user-1", tenant_id="tenant-1", instance_id="instance-1", phone="+15551234567"):
    return TenantContext(
        tenant_id=tenant_id,
        user_id=user_id,
        instance_id=instance_id,
        phone_number=phone,
        status="active",
    )


def test_detect_cross_tenant_attempt_blocks_payload_user(resolver_stub):
    payload = {"user_id": "external-user"}
    assert resolver_stub.detect_cross_tenant_attempt(payload, "tenant-verified") is True


def test_validate_phone_ownership_rejects_conflicting_owner(resolver_stub):
    tenant_context = _make_tenant_context()
    conflicting_owner = WAPIInstance(
        tenant_id="tenant-2",
        user_id="user-2",
        wapi_instance_id="instance-2",
        instance_name="conflict",
        phone_number="+1 (555) 123-4567",
        status="active",
        api_key_hash="hash",
    )
    resolver_stub.instances_repo.get_owner_by_phone.return_value = conflicting_owner

    assert resolver_stub.validate_phone_ownership("15551234567@s.whatsapp.net", tenant_context) is False


def test_validate_phone_ownership_accepts_same_user(resolver_stub):
    tenant_context = _make_tenant_context()
    owner = WAPIInstance(
        tenant_id=tenant_context.tenant_id,
        user_id=tenant_context.user_id,
        wapi_instance_id="instance-1",
        instance_name="primary",
        phone_number=tenant_context.phone_number,
        status="active",
        api_key_hash="hash",
    )
    resolver_stub.instances_repo.get_owner_by_phone.return_value = owner

    assert resolver_stub.validate_phone_ownership("+1 555 123 4567", tenant_context) is True


@pytest.mark.asyncio
async def test_validate_and_resolve_rejects_payload_user_override(resolver_stub):
    tenant_context = _make_tenant_context()

    resolver_stub.resolve_from_instance = AsyncMock(return_value=tenant_context)
    resolver_stub.validate_phone_ownership = Mock(return_value=True)

    middleware = TenantIsolationMiddleware.__new__(TenantIsolationMiddleware)
    middleware.resolver = resolver_stub

    tenant, errors = await middleware.validate_and_resolve(
        instance_id="instance-1",
        sender_phone="15551234567",
        payload={"user_id": "attacker"},
    )

    assert tenant is None
    assert errors.get("payload_forbidden_fields") == "Payload attempted to override tenant/user context"
