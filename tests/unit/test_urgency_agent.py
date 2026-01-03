"""Unit tests for Urgency Agent."""

import pytest
import json
from datetime import datetime
from unittest.mock import AsyncMock, patch

from jaiminho_notificacoes.processing.agents import (
    UrgencyAgent,
    UrgencyResult,
    HistoricalInterruptionData,
)
from jaiminho_notificacoes.persistence.models import (
    NormalizedMessage,
    MessageType,
    MessageContent,
    MessageMetadata,
    MessageSecurity,
    MessageSource as MessageSourceModel
)


@pytest.fixture
def base_message():
    """Create a base message for testing."""
    return NormalizedMessage(
        message_id="test-msg-123",
        tenant_id="tenant-abc",
        user_id="user-xyz",
        sender_phone="5511999999999",
        sender_name="Test User",
        message_type=MessageType.TEXT,
        content=MessageContent(text="Test message"),
        timestamp=int(datetime.utcnow().timestamp()),
        source=MessageSourceModel(
            platform="evolution_api",
            instance_id="test-instance"
        ),
        metadata=MessageMetadata(is_group=False, from_me=False),
        security=MessageSecurity(
            validated_at=datetime.utcnow().isoformat(),
            validation_passed=True,
            instance_verified=True,
            tenant_resolved=True,
            phone_ownership_verified=True
        )
    )


@pytest.fixture
def urgency_agent():
    """Create urgency agent instance."""
    return UrgencyAgent()


@pytest.fixture
def historical_data_empty():
    """Empty historical data (first contact)."""
    return HistoricalInterruptionData(sender_phone="5511999999999")


@pytest.fixture
def historical_data_low_urgency():
    """Historical data with low urgency rate."""
    return HistoricalInterruptionData(
        sender_phone="5511999999999",
        total_messages=20,
        urgent_count=1,
        not_urgent_count=19,
        avg_response_time_seconds=3600.0
    )


@pytest.fixture
def historical_data_high_urgency():
    """Historical data with high urgency rate."""
    return HistoricalInterruptionData(
        sender_phone="5511999999999",
        total_messages=15,
        urgent_count=12,
        not_urgent_count=3,
        avg_response_time_seconds=300.0,
        last_urgent_timestamp=int(datetime.utcnow().timestamp()) - 7200
    )


class TestUrgencyResult:
    """Test UrgencyResult dataclass."""
    
    def test_to_json(self):
        """Test JSON serialization."""
        result = UrgencyResult(
            urgent=True,
            reason="Financial alert detected",
            confidence=0.87654321
        )
        
        json_data = result.to_json()
        
        assert json_data["urgent"] is True
        assert json_data["reason"] == "Financial alert detected"
        assert json_data["confidence"] == 0.877  # Rounded to 3 decimals


class TestHistoricalInterruptionData:
    """Test HistoricalInterruptionData."""
    
    def test_urgency_rate_calculation(self):
        """Test urgency rate calculation."""
        data = HistoricalInterruptionData(
            sender_phone="5511999999999",
            urgent_count=3,
            not_urgent_count=7
        )
        
        assert data.urgency_rate == 0.3
    
    def test_urgency_rate_zero_messages(self):
        """Test urgency rate with no messages."""
        data = HistoricalInterruptionData(sender_phone="5511999999999")
        
        assert data.urgency_rate == 0.0


class TestUrgencyAgent:
    """Test UrgencyAgent functionality."""
    
    @pytest.mark.asyncio
    async def test_empty_message_not_urgent(self, urgency_agent, base_message, historical_data_empty):
        """Empty messages should never be urgent."""
        base_message.content.text = ""
        
        result = await urgency_agent.run(base_message, historical_data_empty)
        
        assert result.urgent is False
        assert result.confidence >= 0.8
        assert "vazia" in result.reason.lower() or "curta" in result.reason.lower()
    
    @pytest.mark.asyncio
    async def test_very_short_message_not_urgent(self, urgency_agent, base_message, historical_data_empty):
        """Very short messages should not be urgent."""
        base_message.content.text = "Ok"
        
        result = await urgency_agent.run(base_message, historical_data_empty)
        
        assert result.urgent is False
        assert result.confidence >= 0.8
    
    @pytest.mark.asyncio
    async def test_group_message_not_urgent(self, urgency_agent, base_message, historical_data_empty):
        """Group messages should not be urgent by default."""
        base_message.content.text = "Urgente! Precisamos conversar agora!"
        base_message.metadata.is_group = True
        
        result = await urgency_agent.run(base_message, historical_data_empty)
        
        assert result.urgent is False
        assert result.confidence >= 0.8
        assert "grupo" in result.reason.lower()
    
    @pytest.mark.asyncio
    async def test_error_handling_conservative_fallback(self, urgency_agent, base_message):
        """Errors should result in conservative (not urgent) fallback."""
        base_message.content.text = "Test message"
        
        # Mock LLM to raise exception
        with patch.object(urgency_agent, '_call_llm', side_effect=Exception("API Error")):
            result = await urgency_agent.run(base_message)
        
        assert result.urgent is False
        assert "erro" in result.reason.lower()
        assert result.confidence <= 0.6
    
    @pytest.mark.asyncio
    async def test_parse_urgency_response_valid_json(self, urgency_agent):
        """Test parsing valid JSON response."""
        response = json.dumps({
            "urgent": True,
            "confidence": 0.92,
            "reason": "Alerta financeiro detectado",
            "keywords_detected": ["pix", "fraude"]
        })
        
        result = urgency_agent._parse_urgency_response(response)
        
        assert result.urgent is True
        assert result.confidence == 0.92
        assert "financeiro" in result.reason.lower()
    
    @pytest.mark.asyncio
    async def test_parse_urgency_response_with_markdown(self, urgency_agent):
        """Test parsing JSON wrapped in markdown code blocks."""
        response = """```json
{
  "urgent": false,
  "confidence": 0.75,
  "reason": "Mensagem informativa"
}
```"""
        
        result = urgency_agent._parse_urgency_response(response)
        
        assert result.urgent is False
        assert result.confidence == 0.75
    
    @pytest.mark.asyncio
    async def test_parse_urgency_response_invalid_json(self, urgency_agent):
        """Test parsing invalid JSON - should return conservative fallback."""
        response = "This is not JSON"
        
        result = urgency_agent._parse_urgency_response(response)
        
        assert result.urgent is False
        assert result.confidence <= 0.5
        assert "erro" in result.reason.lower()
    
    @pytest.mark.asyncio
    async def test_parse_urgency_response_clamps_confidence(self, urgency_agent):
        """Test that confidence is clamped to [0, 1]."""
        response = json.dumps({
            "urgent": True,
            "confidence": 1.5,  # Invalid, > 1
            "reason": "Test"
        })
        
        result = urgency_agent._parse_urgency_response(response)
        
        assert result.confidence == 1.0
        
        response = json.dumps({
            "urgent": False,
            "confidence": -0.2,  # Invalid, < 0
            "reason": "Test"
        })
        
        result = urgency_agent._parse_urgency_response(response)
        
        assert result.confidence == 0.0


class TestConservativeLogic:
    """Test conservative decision-making logic."""
    
    @pytest.mark.asyncio
    async def test_low_confidence_override(self, urgency_agent, base_message, historical_data_empty):
        """Low confidence urgent decisions should be overridden."""
        result = UrgencyResult(
            urgent=True,
            reason="Possível urgência",
            confidence=0.65  # Below threshold
        )
        
        adjusted = urgency_agent._apply_conservative_logic(
            result,
            historical_data_empty,
            base_message
        )
        
        assert adjusted.urgent is False
        assert "confiança insuficiente" in adjusted.reason.lower()
    
    @pytest.mark.asyncio
    async def test_first_contact_requires_high_confidence(self, urgency_agent, base_message, historical_data_empty):
        """First contact should require very high confidence."""
        result = UrgencyResult(
            urgent=True,
            reason="Possível urgência",
            confidence=0.80  # Good, but not enough for first contact
        )
        
        adjusted = urgency_agent._apply_conservative_logic(
            result,
            historical_data_empty,
            base_message
        )
        
        assert adjusted.urgent is False
        assert "primeiro contato" in adjusted.reason.lower()
    
    @pytest.mark.asyncio
    async def test_first_contact_very_high_confidence_allowed(self, urgency_agent, base_message, historical_data_empty):
        """First contact with very high confidence should be allowed."""
        result = UrgencyResult(
            urgent=True,
            reason="Código de verificação detectado",
            confidence=0.90  # Very high
        )
        
        adjusted = urgency_agent._apply_conservative_logic(
            result,
            historical_data_empty,
            base_message
        )
        
        assert adjusted.urgent is True
    
    @pytest.mark.asyncio
    async def test_low_historical_urgency_rate_conservative(self, urgency_agent, base_message, historical_data_low_urgency):
        """Low historical urgency rate should make agent more conservative."""
        result = UrgencyResult(
            urgent=True,
            reason="Possível urgência",
            confidence=0.78
        )
        
        adjusted = urgency_agent._apply_conservative_logic(
            result,
            historical_data_low_urgency,
            base_message
        )
        
        assert adjusted.urgent is False
        assert "histórico" in adjusted.reason.lower()
    
    @pytest.mark.asyncio
    async def test_high_historical_urgency_rate_less_conservative(self, urgency_agent, base_message, historical_data_high_urgency):
        """High historical urgency rate should be less conservative."""
        result = UrgencyResult(
            urgent=True,
            reason="Alerta detectado",
            confidence=0.78
        )
        
        adjusted = urgency_agent._apply_conservative_logic(
            result,
            historical_data_high_urgency,
            base_message
        )
        
        # With high historical urgency, should still be urgent
        assert adjusted.urgent is True
    
    @pytest.mark.asyncio
    async def test_group_message_requires_very_high_confidence(self, urgency_agent, base_message, historical_data_empty):
        """Group messages need very high confidence to interrupt."""
        base_message.metadata.is_group = True
        
        result = UrgencyResult(
            urgent=True,
            reason="Possível urgência",
            confidence=0.85
        )
        
        adjusted = urgency_agent._apply_conservative_logic(
            result,
            historical_data_empty,
            base_message
        )
        
        assert adjusted.urgent is False
        assert "grupo" in adjusted.reason.lower()
    
    @pytest.mark.asyncio
    async def test_known_sender_lower_threshold(self, urgency_agent, base_message):
        """Known senders with good history should have lower threshold."""
        historical_data = HistoricalInterruptionData(
            sender_phone="5511999999999",
            total_messages=10,
            urgent_count=3,
            not_urgent_count=7
        )
        
        result = UrgencyResult(
            urgent=True,
            reason="Alerta detectado",
            confidence=0.68  # Between KNOWN and URGENT thresholds
        )
        
        adjusted = urgency_agent._apply_conservative_logic(
            result,
            historical_data,
            base_message
        )
        
        # Should remain urgent due to known sender
        assert adjusted.urgent is True


class TestPromptBuilding:
    """Test prompt construction."""
    
    def test_build_prompt_with_history(self, urgency_agent, base_message, historical_data_high_urgency):
        """Test prompt includes historical data."""
        base_message.content.text = "Test message content"
        
        prompt = urgency_agent._build_urgency_prompt(
            base_message,
            base_message.content.text,
            historical_data_high_urgency,
            ""
        )
        
        assert "DADOS HISTÓRICOS" in prompt
        assert "Total de mensagens" in prompt
        assert "Taxa de urgência histórica" in prompt
        assert str(historical_data_high_urgency.total_messages) in prompt
    
    def test_build_prompt_first_contact(self, urgency_agent, base_message, historical_data_empty):
        """Test prompt for first contact."""
        base_message.content.text = "Test message"
        
        prompt = urgency_agent._build_urgency_prompt(
            base_message,
            base_message.content.text,
            historical_data_empty,
            ""
        )
        
        assert "Nenhum histórico disponível" in prompt or "primeiro contato" in prompt.lower()
    
    def test_build_prompt_conservative_instructions(self, urgency_agent, base_message, historical_data_empty):
        """Test that prompt includes conservative instructions."""
        base_message.content.text = "Test"
        
        prompt = urgency_agent._build_urgency_prompt(
            base_message,
            base_message.content.text,
            historical_data_empty,
            ""
        )
        
        assert "SEJA CONSERVADOR" in prompt.upper()
        assert "NÃO interrompa" in prompt or "não interromper" in prompt.lower()


class TestIntegration:
    """Integration tests with mocked LLM."""
    
    @pytest.mark.asyncio
    async def test_full_flow_urgent_financial(self, urgency_agent, base_message, historical_data_high_urgency):
        """Test full flow with urgent financial message."""
        base_message.content.text = "ALERTA: Transação suspeita de R$ 5.000,00 detectada em sua conta. Código de verificação: 123456"
        
        # Mock LLM response
        mock_response = json.dumps({
            "urgent": True,
            "confidence": 0.95,
            "reason": "Alerta financeiro crítico com código de verificação",
            "keywords_detected": ["alerta", "transação suspeita", "código de verificação"]
        })
        
        with patch.object(urgency_agent, '_call_llm', return_value=mock_response):
            result = await urgency_agent.run(base_message, historical_data_high_urgency)
        
        assert result.urgent is True
        assert result.confidence >= 0.85
    
    @pytest.mark.asyncio
    async def test_full_flow_not_urgent_marketing(self, urgency_agent, base_message, historical_data_low_urgency):
        """Test full flow with marketing message."""
        base_message.content.text = "Promoção especial! 50% de desconto em todos os produtos. Não perca!"
        
        # Mock LLM response
        mock_response = json.dumps({
            "urgent": False,
            "confidence": 0.88,
            "reason": "Mensagem de marketing/promoção",
            "keywords_detected": ["promoção", "desconto"]
        })
        
        with patch.object(urgency_agent, '_call_llm', return_value=mock_response):
            result = await urgency_agent.run(base_message, historical_data_low_urgency)
        
        assert result.urgent is False
        assert result.confidence >= 0.7
    
    @pytest.mark.asyncio
    async def test_full_flow_override_low_confidence(self, urgency_agent, base_message, historical_data_empty):
        """Test that low confidence urgent is overridden."""
        base_message.content.text = "Mensagem importante talvez?"
        
        # Mock LLM response with low confidence
        mock_response = json.dumps({
            "urgent": True,
            "confidence": 0.55,  # Too low
            "reason": "Palavra 'importante' encontrada",
            "keywords_detected": ["importante"]
        })
        
        with patch.object(urgency_agent, '_call_llm', return_value=mock_response):
            result = await urgency_agent.run(base_message, historical_data_empty)
        
        # Should be overridden to not urgent
        assert result.urgent is False
        assert "confiança insuficiente" in result.reason.lower()
    
    @pytest.mark.asyncio
    async def test_fetch_historical_data_returns_empty(self, urgency_agent):
        """Test historical data fetching (currently returns empty)."""
        data = await urgency_agent._fetch_historical_data(
            "tenant-123",
            "user-456",
            "5511999999999"
        )
        
        assert isinstance(data, HistoricalInterruptionData)
        assert data.sender_phone == "5511999999999"
        assert data.total_messages == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
