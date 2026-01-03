"""Unit tests for Daily Digest Agent."""

import pytest
from datetime import datetime
from unittest.mock import Mock

from jaiminho_notificacoes.core.tenant import TenantContext
from jaiminho_notificacoes.processing.digest_generator import (
    DigestAgent,
    DigestMessage,
    CategoryDigest,
    UserDigest,
    get_digest_agent
)
from jaiminho_notificacoes.persistence.models import (
    NormalizedMessage,
    MessageContent,
    MessageType,
    MessageSource,
    MessageMetadata,
    MessageSecurity
)


@pytest.fixture
def tenant_context():
    """Provide verified tenant context for digest generation."""
    return TenantContext(
        tenant_id="tenant_1",
        user_id="user_1",
        instance_id="inst_1",
        phone_number="5511999999999",
        status="active"
    )


@pytest.fixture
def sample_messages(tenant_context):
    """Create sample messages for testing."""
    base_time = int(datetime(2026, 1, 3, 10, 0).timestamp())
    
    messages = []
    
    # Work message
    msg1 = NormalizedMessage(
        message_id="msg_1",
        tenant_id=tenant_context.tenant_id,
        user_id=tenant_context.user_id,
        sender_phone="5511111111111",
        sender_name="João",
        message_type=MessageType.TEXT,
        content=MessageContent(text="Reunião amanhã às 10h"),
        timestamp=base_time,
        source=MessageSource(platform="wapi", instance_id=tenant_context.instance_id),
        metadata=MessageMetadata(is_group=False),
        security=MessageSecurity(
            validated_at=datetime.now().isoformat(),
            validation_passed=True,
            instance_verified=True,
            tenant_resolved=True,
            phone_ownership_verified=True
        )
    )
    # Add classification data
    msg1.classification_category = "💼 Trabalho e Negócios"
    msg1.classification_summary = "João: Reunião amanhã às 10h"
    messages.append(msg1)
    
    # Delivery message
    msg2 = NormalizedMessage(
        message_id="msg_2",
        tenant_id=tenant_context.tenant_id,
        user_id=tenant_context.user_id,
        sender_phone="5511222222222",
        sender_name="Correios",
        message_type=MessageType.TEXT,
        content=MessageContent(text="Seu pedido foi enviado"),
        timestamp=base_time + 3600,
        source=MessageSource(platform="wapi", instance_id=tenant_context.instance_id),
        metadata=MessageMetadata(is_group=False),
        security=MessageSecurity(
            validated_at=datetime.now().isoformat(),
            validation_passed=True,
            instance_verified=True,
            tenant_resolved=True,
            phone_ownership_verified=True
        )
    )
    msg2.classification_category = "📦 Entregas e Compras"
    msg2.classification_summary = "Correios: Seu pedido foi enviado"
    messages.append(msg2)
    
    # Family message
    msg3 = NormalizedMessage(
        message_id="msg_3",
        tenant_id=tenant_context.tenant_id,
        user_id=tenant_context.user_id,
        sender_phone="5511333333333",
        sender_name="Mãe",
        message_type=MessageType.TEXT,
        content=MessageContent(text="Tudo bem filho?"),
        timestamp=base_time + 7200,
        source=MessageSource(platform="wapi", instance_id=tenant_context.instance_id),
        metadata=MessageMetadata(is_group=False),
        security=MessageSecurity(
            validated_at=datetime.now().isoformat(),
            validation_passed=True,
            instance_verified=True,
            tenant_resolved=True,
            phone_ownership_verified=True
        )
    )
    msg3.classification_category = "👨‍👩‍👧 Família e Amigos"
    msg3.classification_summary = "Mãe: Tudo bem filho?"
    messages.append(msg3)
    
    return messages


class TestDigestAgent:
    """Test suite for DigestAgent."""
    
    def test_agent_initialization(self):
        """Test that agent initializes correctly."""
        agent = DigestAgent()
        assert agent is not None
        assert agent.logger is not None
    
    @pytest.mark.asyncio
    async def test_generate_digest_basic(self, tenant_context, sample_messages):
        """Test basic digest generation."""
        agent = DigestAgent()
        
        digest = await agent.generate_digest(
            tenant_context=tenant_context,
            messages=sample_messages,
            date="2026-01-03"
        )
        
        assert digest.user_id == tenant_context.user_id
        assert digest.tenant_id == tenant_context.tenant_id
        assert digest.total_messages == 3
        assert len(digest.categories) == 3
    
    @pytest.mark.asyncio
    async def test_generate_digest_empty(self, tenant_context):
        """Test digest generation with no messages."""
        agent = DigestAgent()
        
        digest = await agent.generate_digest(
            tenant_context=tenant_context,
            messages=[],
            date="2026-01-03"
        )
        
        assert digest.total_messages == 0
        assert len(digest.categories) == 0
    
    @pytest.mark.asyncio
    async def test_user_isolation_validation(self, tenant_context, sample_messages):
        """Test that user isolation is enforced."""
        agent = DigestAgent()
        
        # Valid case - all messages for user_1
        digest = await agent.generate_digest(
            tenant_context=tenant_context,
            messages=sample_messages
        )
        assert digest.user_id == tenant_context.user_id
        
        # Invalid case - message from different user
        invalid_msg = sample_messages[0].model_copy(update={"user_id": "user_2"})
        
        with pytest.raises(ValueError, match="Cross-user data"):
            await agent.generate_digest(
                tenant_context=tenant_context,
                messages=[invalid_msg]
            )
    
    @pytest.mark.asyncio
    async def test_whatsapp_text_formatting_with_messages(self, tenant_context, sample_messages):
        """Test WhatsApp formatting with messages."""
        agent = DigestAgent()
        
        digest = await agent.generate_digest(
            tenant_context=tenant_context,
            messages=sample_messages
        )
        
        text = digest.to_whatsapp_text()
        
        # Check header
        assert "Digest Diário" in text
        assert "3 mensagens" in text
        
        # Check categories present
        assert "Trabalho" in text or "💼" in text
        assert "Entregas" in text or "📦" in text
        
        # Check formatting
        assert "*" in text  # Bold markers
        assert "•" in text  # Bullet points
    
    def test_singleton_pattern(self):
        """Test that get_digest_agent returns singleton."""
        agent1 = get_digest_agent()
        agent2 = get_digest_agent()
        
        assert agent1 is agent2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
