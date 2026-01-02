"""Unit tests for Urgency Rule Engine."""

import pytest
from datetime import datetime

from jaiminho_notificacoes.processing.urgency_engine import (
    UrgencyRuleEngine,
    UrgencyDecision,
    KeywordMatcher,
    get_rule_engine
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
        content=MessageContent(text=""),
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


class TestKeywordMatcher:
    """Test keyword matching functionality."""
    
    def test_match_financial_keywords(self):
        """Test matching financial keywords."""
        matcher = KeywordMatcher()
        text = "Seu PIX de R$ 150,00 foi aprovado"
        
        matches = matcher.match_keywords(text, matcher.financial_keywords)
        
        assert len(matches) > 0
        assert 'pix' in [m.lower() for m in matches]
        assert 'aprovado' in [m.lower() for m in matches]
    
    def test_match_security_keywords(self):
        """Test matching security keywords."""
        matcher = KeywordMatcher()
        text = "Seu código de verificação é 123456"
        
        matches = matcher.match_keywords(text, matcher.security_keywords)
        
        assert len(matches) > 0
        assert 'código' in [m.lower() for m in matches]
        assert 'verificação' in [m.lower() for m in matches]
    
    def test_match_marketing_keywords(self):
        """Test matching marketing keywords."""
        matcher = KeywordMatcher()
        text = "Promoção Black Friday! 50% de desconto"
        
        matches = matcher.match_keywords(text, matcher.marketing_keywords)
        
        assert len(matches) >= 2
        assert 'promoção' in [m.lower() for m in matches]
        assert 'desconto' in [m.lower() for m in matches]
    
    def test_financial_patterns(self):
        """Test financial regex patterns."""
        matcher = KeywordMatcher()
        
        # Currency amounts
        matches = matcher.match_patterns("Valor: R$ 1.234,56", matcher.financial_patterns)
        assert len(matches) > 0
        
        # PIX
        matches = matcher.match_patterns("Transferência PIX realizada", matcher.financial_patterns)
        assert len(matches) > 0
    
    def test_security_patterns(self):
        """Test security regex patterns."""
        matcher = KeywordMatcher()
        
        # OTP codes
        matches = matcher.match_patterns("Seu código: 123456", matcher.security_patterns)
        assert len(matches) > 0
        
        # Token patterns
        matches = matcher.match_patterns("Token: ABC123XYZ", matcher.security_patterns)
        assert len(matches) > 0


class TestUrgencyRuleEngine:
    """Test urgency rule engine decisions."""
    
    def test_group_message_not_urgent(self, base_message):
        """Test that group messages are classified as not urgent."""
        engine = UrgencyRuleEngine()
        base_message.metadata.is_group = True
        base_message.content.text = "Reunião amanhã às 10h"
        
        result = engine.evaluate(base_message)
        
        assert result.decision == UrgencyDecision.NOT_URGENT
        assert result.rule_name == "group_message"
        assert result.confidence > 0.9
    
    def test_financial_message_urgent(self, base_message):
        """Test that financial messages are classified as urgent."""
        engine = UrgencyRuleEngine()
        base_message.content.text = "Sua fatura de R$ 350,00 vence amanhã. Pague via PIX."
        
        result = engine.evaluate(base_message)
        
        assert result.decision == UrgencyDecision.URGENT
        assert result.rule_name == "financial_content"
        assert len(result.matched_keywords) > 0
        assert result.confidence > 0.8
    
    def test_security_message_urgent(self, base_message):
        """Test that security messages are classified as urgent."""
        engine = UrgencyRuleEngine()
        base_message.content.text = "Seu código de verificação é 456789. Válido por 5 minutos."
        
        result = engine.evaluate(base_message)
        
        assert result.decision == UrgencyDecision.URGENT
        assert result.rule_name == "security_content"
        assert len(result.matched_keywords) > 0
    
    def test_marketing_message_not_urgent(self, base_message):
        """Test that marketing messages are classified as not urgent."""
        engine = UrgencyRuleEngine()
        base_message.content.text = "Promoção imperdível! 70% de desconto. Aproveite agora!"
        
        result = engine.evaluate(base_message)
        
        assert result.decision == UrgencyDecision.NOT_URGENT
        assert result.rule_name == "marketing_content"
        assert len(result.matched_keywords) >= 2
    
    def test_empty_message_not_urgent(self, base_message):
        """Test that empty messages are not urgent."""
        engine = UrgencyRuleEngine()
        base_message.content.text = ""
        
        result = engine.evaluate(base_message)
        
        assert result.decision == UrgencyDecision.NOT_URGENT
        assert result.rule_name == "empty_or_short"
    
    def test_generic_message_undecided(self, base_message):
        """Test that generic messages return undecided."""
        engine = UrgencyRuleEngine()
        base_message.content.text = "Oi, tudo bem? Como você está?"
        
        result = engine.evaluate(base_message)
        
        assert result.decision == UrgencyDecision.UNDECIDED
        assert result.rule_name == "no_match"
        assert result.confidence == 0.0


class TestSpecificScenarios:
    """Test specific real-world scenarios."""
    
    def test_bank_alert_urgent(self, base_message):
        """Test bank alert is urgent."""
        engine = UrgencyRuleEngine()
        base_message.content.text = """
        Alerta Itaú: Compra no cartão final 1234
        Valor: R$ 499,90
        Local: Amazon
        Se não reconhece, bloqueie o cartão
        """
        
        result = engine.evaluate(base_message)
        
        assert result.decision == UrgencyDecision.URGENT
        assert "financial" in result.rule_name or "security" in result.rule_name
    
    def test_password_reset_urgent(self, base_message):
        """Test password reset is urgent."""
        engine = UrgencyRuleEngine()
        base_message.content.text = "Código para redefinir sua senha: 789012. Expira em 10 minutos."
        
        result = engine.evaluate(base_message)
        
        assert result.decision == UrgencyDecision.URGENT
        assert result.rule_name == "security_content"
    
    def test_newsletter_not_urgent(self, base_message):
        """Test newsletter is not urgent."""
        engine = UrgencyRuleEngine()
        base_message.content.text = """
        Newsletter Semanal
        
        Confira as novidades da semana!
        - Novo produto lançado
        - Promoções especiais
        
        Para cancelar inscrição, clique aqui
        """
        
        result = engine.evaluate(base_message)
        
        assert result.decision == UrgencyDecision.NOT_URGENT
        assert result.rule_name == "marketing_content"
    
    def test_pix_received_urgent(self, base_message):
        """Test PIX received notification is urgent."""
        engine = UrgencyRuleEngine()
        base_message.content.text = "PIX recebido de João Silva - R$ 1.500,00"
        
        result = engine.evaluate(base_message)
        
        assert result.decision == UrgencyDecision.URGENT
        assert result.rule_name == "financial_content"
    
    def test_fraud_alert_urgent(self, base_message):
        """Test fraud alert is urgent."""
        engine = UrgencyRuleEngine()
        base_message.content.text = """
        ALERTA DE SEGURANÇA
        Tentativa de acesso suspeito detectada na sua conta
        Local: São Paulo, SP
        Se não foi você, altere sua senha imediatamente
        """
        
        result = engine.evaluate(base_message)
        
        assert result.decision == UrgencyDecision.URGENT
    
    def test_promotional_campaign_not_urgent(self, base_message):
        """Test promotional campaign is not urgent."""
        engine = UrgencyRuleEngine()
        base_message.content.text = """
        🎉 MEGA PROMOÇÃO 🎉
        
        Compre 2 e leve 3!
        Até 60% OFF em produtos selecionados
        
        Válido até domingo
        """
        
        result = engine.evaluate(base_message)
        
        assert result.decision == UrgencyDecision.NOT_URGENT


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_mixed_content_financial_wins(self, base_message):
        """Test that financial keywords win over marketing."""
        engine = UrgencyRuleEngine()
        base_message.content.text = """
        Aproveite nossa promoção!
        Pague sua fatura com desconto via PIX
        Valor: R$ 200,00
        """
        
        result = engine.evaluate(base_message)
        
        # Financial should be evaluated first and win
        assert result.decision == UrgencyDecision.URGENT
    
    def test_case_insensitive_matching(self, base_message):
        """Test that keyword matching is case-insensitive."""
        engine = UrgencyRuleEngine()
        base_message.content.text = "CÓDIGO DE VERIFICAÇÃO: 123456"
        
        result = engine.evaluate(base_message)
        
        assert result.decision == UrgencyDecision.URGENT
    
    def test_special_characters_in_amount(self, base_message):
        """Test currency amount with special characters."""
        engine = UrgencyRuleEngine()
        base_message.content.text = "Transferência de R$ 1.234.567,89 realizada"
        
        result = engine.evaluate(base_message)
        
        assert result.decision == UrgencyDecision.URGENT
    
    def test_very_long_message(self, base_message):
        """Test handling of very long messages."""
        engine = UrgencyRuleEngine()
        base_message.content.text = "Mensagem normal " * 1000 + " com PIX no final"
        
        result = engine.evaluate(base_message)
        
        # Should still detect PIX keyword
        assert result.decision == UrgencyDecision.URGENT


class TestEngineStats:
    """Test rule engine statistics."""
    
    def test_stats_tracking(self, base_message):
        """Test that statistics are tracked correctly."""
        engine = UrgencyRuleEngine()
        
        # Process multiple messages
        base_message.content.text = "PIX de R$ 100"
        engine.evaluate(base_message)
        
        base_message.content.text = "Promoção 50% desconto aproveite"
        engine.evaluate(base_message)
        
        base_message.content.text = "Olá, como vai?"
        engine.evaluate(base_message)
        
        stats = engine.get_stats()
        
        assert stats['total_evaluations'] == 3
        assert stats['urgent_decisions'] == 1
        assert stats['not_urgent_decisions'] == 1
        assert stats['undecided'] == 1
    
    def test_reset_stats(self, base_message):
        """Test stats reset functionality."""
        engine = UrgencyRuleEngine()
        
        base_message.content.text = "PIX de R$ 100"
        engine.evaluate(base_message)
        
        engine.reset_stats()
        stats = engine.get_stats()
        
        assert stats['total_evaluations'] == 0


def test_get_rule_engine_singleton():
    """Test that get_rule_engine returns singleton."""
    engine1 = get_rule_engine()
    engine2 = get_rule_engine()
    
    assert engine1 is engine2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
