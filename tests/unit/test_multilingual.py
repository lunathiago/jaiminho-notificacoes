"""Tests for multilingual keyword and pattern support.

Validates that the rule engine correctly classifies messages in:
- Portuguese (PT-BR)
- English (EN)
- Spanish (ES)
"""

import pytest
from unittest.mock import MagicMock, patch

from jaiminho_notificacoes.processing.urgency_engine import (
    UrgencyRuleEngine,
    UrgencyDecision,
    KeywordMatcher,
)
from jaiminho_notificacoes.persistence.models import (
    NormalizedMessage,
    MessageMetadata,
    MessageContent,
    MessageType,
    MessageSource,
    MessageSecurity,
)
from datetime import datetime


@pytest.fixture
def rule_engine():
    """Create a fresh rule engine instance."""
    return UrgencyRuleEngine()


@pytest.fixture
def matcher():
    """Create a fresh keyword matcher."""
    return KeywordMatcher()


def create_test_message(
    message_id: str,
    user_id: str,
    text: str,
    sender_phone: str = "551199999999",
    sender_name: str = "Test Sender",
    is_group: bool = False
) -> NormalizedMessage:
    """Helper to create test messages with proper schema."""
    import time
    return NormalizedMessage(
        message_id=message_id,
        tenant_id="tenant_1",
        user_id=user_id,
        sender_phone=sender_phone,
        sender_name=sender_name,
        message_type=MessageType.TEXT,
        content=MessageContent(text=text),
        timestamp=int(time.time()),
        source=MessageSource(platform="wapi", instance_id="inst_123"),
        metadata=MessageMetadata(chat_type="group" if is_group else "individual", is_group=is_group),
        security=MessageSecurity(
            validated_at=datetime.now().isoformat(),
            validation_passed=True,
            instance_verified=True,
            tenant_resolved=True,
            phone_ownership_verified=True
        )
    )



class TestMultilingualFinancialKeywords:
    """Test financial keywords across languages."""
    
    def test_portuguese_banking_keywords(self, matcher):
        """Test PT-BR banking keywords are present."""
        assert 'banco' in matcher.financial_keywords
        assert 'conta' in matcher.financial_keywords
        assert 'pix' in matcher.financial_keywords
        assert 'boleto' in matcher.financial_keywords
        assert 'cartão' in matcher.financial_keywords
        assert 'transferência' in matcher.financial_keywords
    
    def test_english_banking_keywords(self, matcher):
        """Test English banking keywords are present."""
        assert 'bank' in matcher.financial_keywords
        assert 'account' in matcher.financial_keywords
        assert 'transfer' in matcher.financial_keywords
        assert 'card' in matcher.financial_keywords
        assert 'invoice' in matcher.financial_keywords
        assert 'payment' in matcher.financial_keywords
    
    def test_spanish_banking_keywords(self, matcher):
        """Test ES banking keywords are present."""
        assert 'banco' in matcher.financial_keywords
        assert 'cuenta' in matcher.financial_keywords
        assert 'tarjeta' in matcher.financial_keywords
        assert 'transferencia' in matcher.financial_keywords
        assert 'factura' in matcher.financial_keywords
        assert 'pago' in matcher.financial_keywords
    
    def test_portuguese_transaction_keywords(self, matcher):
        """Test PT-BR transaction keywords."""
        assert 'transação' in matcher.financial_keywords
        assert 'compra' in matcher.financial_keywords
        assert 'aprovado' in matcher.financial_keywords
        assert 'pendente' in matcher.financial_keywords
    
    def test_english_transaction_keywords(self, matcher):
        """Test English transaction keywords."""
        assert 'transaction' in matcher.financial_keywords
        assert 'purchase' in matcher.financial_keywords
        assert 'approved' in matcher.financial_keywords
        assert 'pending' in matcher.financial_keywords
    
    def test_spanish_transaction_keywords(self, matcher):
        """Test ES transaction keywords."""
        assert 'transacción' in matcher.financial_keywords
        assert 'compra' in matcher.financial_keywords
        assert 'aprobado' in matcher.financial_keywords
        assert 'pendiente' in matcher.financial_keywords
    
    def test_currency_codes_supported(self, matcher):
        """Test multiple currency codes are recognized."""
        # PT-BR currencies
        assert 'r$' in matcher.financial_keywords
        assert 'brl' in matcher.financial_keywords
        
        # Universal
        assert 'usd' in matcher.financial_keywords
        assert 'euro' in matcher.financial_keywords
        
        # Spanish America
        assert 'mxn' in matcher.financial_keywords  # Mexico
        assert 'ars' in matcher.financial_keywords  # Argentina
        assert 'clp' in matcher.financial_keywords  # Chile
        assert 'cop' in matcher.financial_keywords  # Colombia


class TestMultilingualSecurityKeywords:
    """Test security keywords across languages."""
    
    def test_portuguese_auth_keywords(self, matcher):
        """Test PT-BR authentication keywords."""
        assert 'senha' in matcher.security_keywords
        assert 'código' in matcher.security_keywords
        assert 'autenticação' in matcher.security_keywords
        assert 'verificação' in matcher.security_keywords
    
    def test_english_auth_keywords(self, matcher):
        """Test English authentication keywords."""
        assert 'password' in matcher.security_keywords
        assert 'code' in matcher.security_keywords
        assert 'authentication' in matcher.security_keywords
        assert 'verification' in matcher.security_keywords
    
    def test_spanish_auth_keywords(self, matcher):
        """Test ES authentication keywords."""
        assert 'contraseña' in matcher.security_keywords
        assert 'código' in matcher.security_keywords
        assert 'autenticación' in matcher.security_keywords
        assert 'verificación' in matcher.security_keywords
    
    def test_portuguese_alert_keywords(self, matcher):
        """Test PT-BR alert keywords."""
        assert 'alerta' in matcher.security_keywords
        assert 'urgente' in matcher.security_keywords
        assert 'crítico' in matcher.security_keywords
        assert 'ação requerida' in matcher.security_keywords
    
    def test_english_alert_keywords(self, matcher):
        """Test English alert keywords."""
        assert 'alert' in matcher.security_keywords
        assert 'urgent' in matcher.security_keywords
        assert 'critical' in matcher.security_keywords
        assert 'action required' in matcher.security_keywords
    
    def test_spanish_alert_keywords(self, matcher):
        """Test ES alert keywords."""
        assert 'alerta' in matcher.security_keywords
        assert 'urgente' in matcher.security_keywords
        assert 'crítico' in matcher.security_keywords
        assert 'acción requerida' in matcher.security_keywords
    
    def test_expiration_keywords_multilingual(self, matcher):
        """Test expiration keywords across languages."""
        # PT-BR
        assert 'expira' in matcher.security_keywords
        assert 'expiração' in matcher.security_keywords
        
        # EN
        assert 'expires' in matcher.security_keywords
        assert 'expiration' in matcher.security_keywords
        
        # ES
        assert 'expiración' in matcher.security_keywords


class TestMultilingualMarketingKeywords:
    """Test marketing keywords across languages."""
    
    def test_portuguese_promotion_keywords(self, matcher):
        """Test PT-BR promotion keywords."""
        assert 'promoção' in matcher.marketing_keywords
        assert 'oferta' in matcher.marketing_keywords
        assert 'desconto' in matcher.marketing_keywords
        assert 'black friday' in matcher.marketing_keywords
    
    def test_english_promotion_keywords(self, matcher):
        """Test English promotion keywords."""
        assert 'promotion' in matcher.marketing_keywords
        assert 'offer' in matcher.marketing_keywords
        assert 'discount' in matcher.marketing_keywords
        assert 'sale' in matcher.marketing_keywords
    
    def test_spanish_promotion_keywords(self, matcher):
        """Test ES promotion keywords."""
        assert 'promoción' in matcher.marketing_keywords
        assert 'oferta' in matcher.marketing_keywords
        assert 'descuento' in matcher.marketing_keywords
        assert 'liquidación' in matcher.marketing_keywords
    
    def test_portuguese_engagement_keywords(self, matcher):
        """Test PT-BR engagement keywords."""
        assert 'clique aqui' in matcher.marketing_keywords
        assert 'saiba mais' in matcher.marketing_keywords
        assert 'conheça' in matcher.marketing_keywords
    
    def test_english_engagement_keywords(self, matcher):
        """Test English engagement keywords."""
        assert 'click here' in matcher.marketing_keywords
        assert 'learn more' in matcher.marketing_keywords
    
    def test_spanish_engagement_keywords(self, matcher):
        """Test ES engagement keywords."""
        assert 'haz clic aquí' in matcher.marketing_keywords
        assert 'aprende más' in matcher.marketing_keywords


class TestMultilingualPatternMatching:
    """Test regex patterns across languages."""
    
    def test_financial_currency_patterns(self, matcher):
        """Test currency symbol patterns."""
        # Portuguese
        assert matcher.match_patterns("Transferência de R$ 500,00", matcher.financial_patterns)
        
        # English
        assert matcher.match_patterns("Transfer of $500.00", matcher.financial_patterns)
        
        # Euro
        assert matcher.match_patterns("Payment of €50,00", matcher.financial_patterns)
    
    def test_financial_bank_transfer_patterns_portuguese(self, matcher):
        """Test PT-BR bank transfer patterns."""
        text = "Transferência de R$ 1.500,00 aprovada"
        matches = matcher.match_patterns(text, matcher.financial_patterns)
        assert len(matches) > 0
    
    def test_financial_bank_transfer_patterns_english(self, matcher):
        """Test English bank transfer patterns."""
        text = "Transfer of $1,500.00 confirmed"
        matches = matcher.match_patterns(text, matcher.financial_patterns)
        assert len(matches) > 0
    
    def test_financial_bank_transfer_patterns_spanish(self, matcher):
        """Test ES bank transfer patterns."""
        text = "Transferencia de $1.500,00 aprobada"
        matches = matcher.match_patterns(text, matcher.financial_patterns)
        assert len(matches) > 0
    
    def test_security_otp_patterns(self, matcher):
        """Test OTP code patterns."""
        # 4-digit OTP (common in PT-BR)
        text = "Your OTP is 1234"
        matches = matcher.match_patterns(text, matcher.security_patterns)
        assert any('1234' in str(m) for m in matches)
        
        # 6-digit OTP (common in EN)
        text = "Your code is 123456"
        matches = matcher.match_patterns(text, matcher.security_patterns)
        assert any('123456' in str(m) for m in matches)
    
    def test_marketing_discount_patterns_portuguese(self, matcher):
        """Test PT-BR discount patterns."""
        text = "Não perca! Até 50% OFF em tudo!"
        matches = matcher.match_patterns(text, matcher.marketing_patterns)
        assert len(matches) > 0
    
    def test_marketing_discount_patterns_english(self, matcher):
        """Test English discount patterns."""
        text = "Don't miss! Up to 50% off all items!"
        matches = matcher.match_patterns(text, matcher.marketing_patterns)
        assert len(matches) > 0
    
    def test_marketing_discount_patterns_spanish(self, matcher):
        """Test ES discount patterns."""
        text = "¡No pierda! Hasta 50% de descuento en todo!"
        matches = matcher.match_patterns(text, matcher.marketing_patterns)
        assert len(matches) > 0


class TestMultilingualClassification:
    """Test full classification flow across languages."""
    
    def test_portuguese_bank_alert_urgent(self, rule_engine):
        """Test PT-BR bank alert is classified as URGENT."""
        message = create_test_message(
            message_id="msg_1",
            user_id="user_1",
            text="Alerta: Transferência de R$ 1.000,00 aprovada em sua conta"
        )
        
        match = rule_engine.evaluate(message)
        assert match.decision == UrgencyDecision.URGENT
        assert match.confidence >= 0.80
    
    def test_english_bank_alert_urgent(self, rule_engine):
        """Test English bank alert is classified as URGENT."""
        message = create_test_message(
            message_id="msg_2",
            user_id="user_1",
            text="Alert: Bank transfer of $1,000.00 approved to your account"
        )
        
        match = rule_engine.evaluate(message)
        assert match.decision == UrgencyDecision.URGENT
        assert match.confidence >= 0.80
    
    def test_spanish_bank_alert_urgent(self, rule_engine):
        """Test ES bank alert is classified as URGENT."""
        message = create_test_message(
            message_id="msg_3",
            user_id="user_1",
            text="Alerta: Transferencia de $1.000,00 aprobada en su cuenta"
        )
        
        match = rule_engine.evaluate(message)
        assert match.decision == UrgencyDecision.URGENT
        assert match.confidence >= 0.80
    
    def test_portuguese_security_alert_urgent(self, rule_engine):
        """Test PT-BR security alert is classified as URGENT."""
        message = create_test_message(
            message_id="msg_4",
            user_id="user_1",
            text="ALERTA: Tentativa de acesso não autorizado. Confirme sua identidade agora"
        )
        
        match = rule_engine.evaluate(message)
        assert match.decision == UrgencyDecision.URGENT
        assert match.confidence >= 0.80
    
    def test_english_security_alert_urgent(self, rule_engine):
        """Test English security alert is classified as URGENT."""
        message = create_test_message(
            message_id="msg_5",
            user_id="user_1",
            text="ALERT: Unauthorized access attempt detected. Confirm your identity now"
        )
        
        match = rule_engine.evaluate(message)
        assert match.decision == UrgencyDecision.URGENT
        assert match.confidence >= 0.80
    
    def test_spanish_security_alert_urgent(self, rule_engine):
        """Test ES security alert is classified as URGENT."""
        message = create_test_message(
            message_id="msg_6",
            user_id="user_1",
            text="ALERTA: Intento de acceso no autorizado detectado. Confirma tu identidad ahora"
        )
        
        match = rule_engine.evaluate(message)
        assert match.decision == UrgencyDecision.URGENT
        assert match.confidence >= 0.80
    
    def test_portuguese_marketing_not_urgent(self, rule_engine):
        """Test PT-BR marketing message is NOT_URGENT."""
        message = create_test_message(
            message_id="msg_7",
            user_id="user_1",
            text="Não perca! Até 50% OFF em todos os produtos. Aproveite enquanto durar!"
        )
        
        match = rule_engine.evaluate(message)
        assert match.decision == UrgencyDecision.NOT_URGENT
        assert match.confidence >= 0.75
    
    def test_english_marketing_not_urgent(self, rule_engine):
        """Test English marketing message is NOT_URGENT."""
        message = create_test_message(
            message_id="msg_8",
            user_id="user_1",
            text="Don't miss! Up to 50% off on all products. Take advantage while stocks last!"
        )
        
        match = rule_engine.evaluate(message)
        assert match.decision == UrgencyDecision.NOT_URGENT
        assert match.confidence >= 0.75
    
    def test_spanish_marketing_not_urgent(self, rule_engine):
        """Test ES marketing message is NOT_URGENT."""
        message = create_test_message(
            message_id="msg_9",
            user_id="user_1",
            text="¡No pierda! Hasta 50% de descuento en todos los productos. ¡Aproveche mientras exista!"
        )
        
        match = rule_engine.evaluate(message)
        assert match.decision == UrgencyDecision.NOT_URGENT
        assert match.confidence >= 0.75


class TestRegionalCurrencies:
    """Test region-specific currencies."""
    
    def test_brazil_real_classification(self, rule_engine):
        """Test Brazilian Real (BRL) classification."""
        message = create_test_message(
            message_id="msg_br",
            user_id="user_br",
            text="Pagamento de R$ 250,00 processado com sucesso"
        )
        
        match = rule_engine.evaluate(message)
        assert match.decision == UrgencyDecision.URGENT
    
    def test_mexico_peso_classification(self, rule_engine):
        """Test Mexican Peso (MXN) classification."""
        message = create_test_message(
            message_id="msg_mx",
            user_id="user_mx",
            text="Transacción de $5.000 MXN completada"
        )
        
        match = rule_engine.evaluate(message)
        assert match.decision == UrgencyDecision.URGENT
    
    def test_argentina_peso_classification(self, rule_engine):
        """Test Argentine Peso (ARS) classification."""
        message = create_test_message(
            message_id="msg_ar",
            user_id="user_ar",
            text="Débito de $1.500 ARS confirmado"
        )
        
        match = rule_engine.evaluate(message)
        assert match.decision == UrgencyDecision.URGENT
    
    def test_euro_classification(self, rule_engine):
        """Test Euro (EUR) classification."""
        message = create_test_message(
            message_id="msg_eu",
            user_id="user_eu",
            text="Payment of €100,50 approved"
        )
        
        match = rule_engine.evaluate(message)
        assert match.decision == UrgencyDecision.URGENT
    
    def test_us_dollar_classification(self, rule_engine):
        """Test US Dollar (USD) classification."""
        message = create_test_message(
            message_id="msg_us",
            user_id="user_us",
            text="Transaction of $500.00 USD processed"
        )
        
        match = rule_engine.evaluate(message)
        assert match.decision == UrgencyDecision.URGENT


class TestMixedLanguageMessages:
    """Test messages with mixed languages."""
    
    def test_portuguese_english_mix(self, rule_engine):
        """Test PT-BR + EN mixed message."""
        message = create_test_message(
            message_id="msg_mix_1",
            user_id="user_1",
            text="Alerta / Alert: Transação / Transaction de $100 USD aprovada / approved"
        )
        
        match = rule_engine.evaluate(message)
        assert match.decision == UrgencyDecision.URGENT
    
    def test_spanish_english_mix(self, rule_engine):
        """Test ES + EN mixed message."""
        message = create_test_message(
            message_id="msg_mix_2",
            user_id="user_1",
            text="Confirmación / Confirmation: Pago de / Payment of $250 MXN"
        )
        
        match = rule_engine.evaluate(message)
        assert match.decision == UrgencyDecision.URGENT


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
