"""Unit tests for Classification Agent."""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime

from jaiminho_notificacoes.processing.agents import (
    ClassificationAgent,
    ClassificationResult
)
from jaiminho_notificacoes.processing.urgency_engine import UrgencyDecision
from jaiminho_notificacoes.persistence.models import (
    NormalizedMessage,
    MessageContent,
    MessageType,
    MessageSource,
    MessageMetadata,
    MessageSecurity
)


@pytest.fixture
def sample_message():
    """Create a sample normalized message for testing."""
    return NormalizedMessage(
        message_id="msg_123",
        tenant_id="tenant_abc",
        user_id="user_xyz",
        sender_phone="5511999999999",
        sender_name="João Silva",
        message_type=MessageType.TEXT,
        content=MessageContent(text="Reunião de projeto amanhã às 10h"),
        timestamp=1609459200,
        source=MessageSource(
            platform="wapi",
            instance_id="instance_1"
        ),
        metadata=MessageMetadata(chat_type="individual", is_group=False),
        security=MessageSecurity(
            validated_at=datetime.utcnow().isoformat(),
            validation_passed=True,
            instance_verified=True,
            tenant_resolved=True,
            phone_ownership_verified=True
        )
    )


class TestClassificationAgent:
    """Test suite for ClassificationAgent."""
    
    def test_agent_initialization(self):
        """Test that agent initializes correctly."""
        agent = ClassificationAgent()
        
        assert agent.model == "gpt-4"
        assert len(agent.CATEGORIES) == 9
        assert "💼 Trabalho e Negócios" in agent.CATEGORIES
        assert "👨‍👩‍👧 Família e Amigos" in agent.CATEGORIES
    
    @pytest.mark.asyncio
    async def test_run_with_valid_message(self, sample_message):
        """Test agent run with valid message."""
        agent = ClassificationAgent()
        
        result = await agent.run(
            message=sample_message,
            urgency_decision=UrgencyDecision.NOT_URGENT,
            urgency_confidence=0.8
        )
        
        assert isinstance(result, ClassificationResult)
        assert result.category in agent.CATEGORIES
        assert len(result.summary) > 0
        assert result.routing in ["immediate", "digest", "spam"]
        assert 0.0 <= result.confidence <= 1.0
    
    @pytest.mark.asyncio
    async def test_tenant_isolation_validation(self, sample_message):
        """Test that tenant isolation is validated."""
        agent = ClassificationAgent()
        
        # Valid message with tenant_id and user_id
        result = await agent.run(
            message=sample_message,
            urgency_decision=UrgencyDecision.NOT_URGENT,
            urgency_confidence=0.7
        )
        
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_tenant_isolation_validation_fails_missing_tenant(self, sample_message):
        """Test that validation fails when tenant_id is missing."""
        agent = ClassificationAgent()
        
        # Create message without tenant_id
        invalid_message = sample_message.copy(update={"tenant_id": ""})
        
        with pytest.raises(ValueError, match="tenant_id"):
            await agent.run(
                message=invalid_message,
                urgency_decision=UrgencyDecision.NOT_URGENT,
                urgency_confidence=0.7
            )
    
    @pytest.mark.asyncio
    async def test_category_assignment_work(self):
        """Test category assignment for work-related messages."""
        agent = ClassificationAgent()
        
        message = NormalizedMessage(
            message_id="msg_work",
            tenant_id="tenant_1",
            user_id="user_1",
            sender_phone="5511999999999",
            sender_name="Gerente",
            message_type=MessageType.TEXT,
            content=MessageContent(text="Reunião de trabalho urgente sobre o projeto"),
            timestamp=1609459200,
            source=MessageSource(platform="wapi", instance_id="inst_1"),
            metadata=MessageMetadata(chat_type="individual", is_group=False),
            security=MessageSecurity(
                validated_at=datetime.utcnow().isoformat(),
                validation_passed=True,
                instance_verified=True,
                tenant_resolved=True,
                phone_ownership_verified=True
            )
        )
        
        result = await agent.run(
            message=message,
            urgency_decision=UrgencyDecision.URGENT,
            urgency_confidence=0.85
        )
        
        # Should be categorized as work
        assert "Trabalho" in result.category or "💼" in result.category
    
    @pytest.mark.asyncio
    async def test_category_assignment_delivery(self):
        """Test category assignment for delivery messages."""
        agent = ClassificationAgent()
        
        message = NormalizedMessage(
            message_id="msg_delivery",
            tenant_id="tenant_1",
            user_id="user_1",
            sender_phone="5511888888888",
            sender_name="Correios",
            message_type=MessageType.TEXT,
            content=MessageContent(text="Seu pedido foi enviado! Código de rastreio: BR123456789"),
            timestamp=1609459200,
            source=MessageSource(platform="wapi", instance_id="inst_1"),
            metadata=MessageMetadata(chat_type="individual", is_group=False),
            security=MessageSecurity(
                validated_at=datetime.utcnow().isoformat(),
                validation_passed=True,
                instance_verified=True,
                tenant_resolved=True,
                phone_ownership_verified=True
            )
        )
        
        result = await agent.run(
            message=message,
            urgency_decision=UrgencyDecision.NOT_URGENT,
            urgency_confidence=0.9
        )
        
        # Should be categorized as delivery
        assert "Entregas" in result.category or "📦" in result.category
    
    @pytest.mark.asyncio
    async def test_summary_generation(self, sample_message):
        """Test that summary is generated correctly."""
        agent = ClassificationAgent()
        
        result = await agent.run(
            message=sample_message,
            urgency_decision=UrgencyDecision.NOT_URGENT,
            urgency_confidence=0.8
        )
        
        # Summary should include sender name
        assert "João Silva" in result.summary or result.summary.startswith("João")
        
        # Summary should be short
        assert len(result.summary) <= 150
        
        # Summary should not be empty
        assert len(result.summary) > 0
    
    @pytest.mark.asyncio
    async def test_routing_urgent_message(self, sample_message):
        """Test routing for urgent messages."""
        agent = ClassificationAgent()
        
        result = await agent.run(
            message=sample_message,
            urgency_decision=UrgencyDecision.URGENT,
            urgency_confidence=0.85
        )
        
        # High-confidence urgent should route to immediate
        assert result.routing == "immediate"
    
    @pytest.mark.asyncio
    async def test_routing_not_urgent_message(self, sample_message):
        """Test routing for non-urgent messages."""
        agent = ClassificationAgent()
        
        result = await agent.run(
            message=sample_message,
            urgency_decision=UrgencyDecision.NOT_URGENT,
            urgency_confidence=0.9
        )
        
        # Not urgent should route to digest
        assert result.routing == "digest"
    
    @pytest.mark.asyncio
    async def test_routing_logic_overrides(self, sample_message):
        """Test that routing logic applies business rules."""
        agent = ClassificationAgent()
        
        # Mock LLM to return "immediate" but with low urgency
        with patch.object(agent, '_call_llm', return_value='''{
            "category": "📰 Informação Geral",
            "summary": "Teste",
            "routing": "immediate",
            "reasoning": "Teste",
            "confidence": 0.7
        }'''):
            result = await agent.run(
                message=sample_message,
                urgency_decision=UrgencyDecision.NOT_URGENT,
                urgency_confidence=0.85
            )
            
            # Should override to digest due to NOT_URGENT decision
            assert result.routing == "digest"
            assert "[Roteamento ajustado" in result.reasoning
    
    @pytest.mark.asyncio
    async def test_fallback_on_error(self, sample_message):
        """Test fallback behavior when agent encounters error."""
        agent = ClassificationAgent()
        
        # Mock LLM to raise exception
        with patch.object(agent, '_call_llm', side_effect=Exception("API Error")):
            result = await agent.run(
                message=sample_message,
                urgency_decision=UrgencyDecision.NOT_URGENT,
                urgency_confidence=0.7
            )
            
            # Should return fallback result
            assert result.category == "❓ Outros"
            assert "Erro" in result.summary or "erro" in result.summary
            assert result.routing == "digest"
            assert result.confidence == 0.5
    
    @pytest.mark.asyncio
    async def test_parse_classification_response_valid(self):
        """Test parsing valid LLM response."""
        agent = ClassificationAgent()
        
        response = '''{
            "category": "💼 Trabalho e Negócios",
            "summary": "Reunião confirmada para amanhã",
            "routing": "digest",
            "reasoning": "Mensagem de trabalho não urgente",
            "confidence": 0.85
        }'''
        
        result = agent._parse_classification_response(response)
        
        assert result.category == "💼 Trabalho e Negócios"
        assert result.summary == "Reunião confirmada para amanhã"
        assert result.routing == "digest"
        assert result.confidence == 0.85
    
    @pytest.mark.asyncio
    async def test_parse_classification_response_invalid_category(self):
        """Test parsing response with invalid category."""
        agent = ClassificationAgent()
        
        response = '''{
            "category": "Invalid Category",
            "summary": "Test",
            "routing": "digest",
            "reasoning": "Test",
            "confidence": 0.7
        }'''
        
        result = agent._parse_classification_response(response)
        
        # Should default to "Outros"
        assert result.category == "❓ Outros"
    
    @pytest.mark.asyncio
    async def test_parse_classification_response_long_summary(self):
        """Test that long summaries are truncated."""
        agent = ClassificationAgent()
        
        long_summary = "A" * 200
        response = f'''{{
            "category": "📰 Informação Geral",
            "summary": "{long_summary}",
            "routing": "digest",
            "reasoning": "Test",
            "confidence": 0.7
        }}'''
        
        result = agent._parse_classification_response(response)
        
        # Summary should be truncated to max 150 chars
        assert len(result.summary) <= 150
        assert result.summary.endswith("...")
    
    @pytest.mark.asyncio
    async def test_parse_classification_response_invalid_json(self):
        """Test parsing invalid JSON response."""
        agent = ClassificationAgent()
        
        response = "This is not JSON"
        
        with pytest.raises(ValueError, match="Invalid JSON"):
            agent._parse_classification_response(response)
    
    def test_validate_tenant_isolation_valid(self, sample_message):
        """Test tenant isolation validation with valid message."""
        agent = ClassificationAgent()
        
        # Should not raise exception
        agent._validate_tenant_isolation(sample_message)
    
    def test_validate_tenant_isolation_missing_tenant(self, sample_message):
        """Test tenant isolation validation with missing tenant_id."""
        agent = ClassificationAgent()
        
        invalid_message = sample_message.copy(update={"tenant_id": ""})
        
        with pytest.raises(ValueError, match="tenant_id"):
            agent._validate_tenant_isolation(invalid_message)
    
    def test_validate_tenant_isolation_missing_user(self, sample_message):
        """Test tenant isolation validation with missing user_id."""
        agent = ClassificationAgent()
        
        invalid_message = sample_message.copy(update={"user_id": ""})
        
        with pytest.raises(ValueError, match="user_id"):
            agent._validate_tenant_isolation(invalid_message)
    
    def test_classification_result_to_json(self):
        """Test ClassificationResult JSON serialization."""
        result = ClassificationResult(
            category="💼 Trabalho e Negócios",
            summary="Reunião confirmada",
            routing="digest",
            reasoning="Não urgente",
            confidence=0.85
        )
        
        json_data = result.to_json()
        
        assert json_data["category"] == "💼 Trabalho e Negócios"
        assert json_data["summary"] == "Reunião confirmada"
        assert json_data["routing"] == "digest"
        assert json_data["reasoning"] == "Não urgente"
        assert json_data["confidence"] == 0.85
    
    @pytest.mark.asyncio
    async def test_no_cross_user_data_used(self, sample_message):
        """
        Test that agent NEVER uses cross-user data.
        
        This is a critical security requirement - the agent should only
        process single-message context without comparing to other users.
        """
        agent = ClassificationAgent()
        
        # Agent should not have any methods that query cross-user data
        assert not hasattr(agent, '_fetch_cross_user_patterns')
        assert not hasattr(agent, '_compare_with_other_users')
        
        # Agent should only receive single message
        result = await agent.run(
            message=sample_message,
            urgency_decision=UrgencyDecision.NOT_URGENT,
            urgency_confidence=0.8,
            tenant_context=None  # No cross-user context
        )
        
        # Result should be based only on this message
        assert result is not None
        assert result.category in agent.CATEGORIES


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
