"""Deterministic urgency detection rule engine (before LLM usage).

This rule engine implements fast, deterministic classification to short-circuit
expensive LLM calls. Rules are evaluated in order of specificity.

Decision Flow:
1. Check group messages → not_urgent
2. Check financial/security keywords → urgent
3. Check marketing/newsletter keywords → not_urgent
4. Check sender patterns → varies
5. Return undecided if no rules match (LLM needed)
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Pattern, Set

from ..core.logger import get_logger
from ..persistence.models import NormalizedMessage, MessageType

logger = get_logger(__name__)


class UrgencyDecision(str, Enum):
    """Urgency classification decisions."""
    URGENT = "urgent"
    NOT_URGENT = "not_urgent"
    UNDECIDED = "undecided"


@dataclass
class RuleMatch:
    """Details about a rule match."""
    decision: UrgencyDecision
    rule_name: str
    confidence: float  # 0.0 to 1.0
    matched_keywords: List[str] = field(default_factory=list)
    reasoning: str = ""


class KeywordMatcher:
    """Efficient keyword and pattern matching with multi-language support."""
    
    def __init__(self):
        # Financial keywords (PT-BR + EN + ES)
        self.financial_keywords = {
            # Banking - Portuguese
            'banco', 'conta', 'saldo', 'transferência', 'pix', 'ted', 'doc',
            'cartão', 'crédito', 'débito', 'fatura', 'boleto', 'pagamento',
            # Banking - English
            'bank', 'account', 'balance', 'transfer', 'card', 'credit', 'debit',
            'invoice', 'payment', 'banking',
            # Banking - Spanish
            'banco', 'cuenta', 'saldo', 'transferencia', 'tarjeta', 'crédito',
            'débito', 'factura', 'pago', 'pagos',
            
            # Transactions - Portuguese
            'transação', 'compra', 'cobrança', 'estorno', 'aprovado', 'negado',
            'pendente', 'processando',
            # Transactions - English
            'transaction', 'purchase', 'charge', 'refund', 'approved', 'denied',
            'pending', 'processing',
            # Transactions - Spanish
            'transacción', 'compra', 'cobro', 'devolución', 'aprobado', 'negado',
            'pendiente', 'procesando',
            
            # Amounts and currency
            'r$', 'brl', 'usd', 'euro', '€', '$', '¥', '£',
            # Spanish currency
            'mxn', 'ars', 'clp', 'cop', 'eur',
            
            # Fraud and security - Portuguese
            'fraude', 'suspeito', 'bloqueio', 'bloqueado', 'tentativa',
            'acesso não autorizado', 'roubo', 'furto',
            # Fraud and security - English
            'fraud', 'suspicious', 'blocked', 'attempt', 'unauthorized access',
            'theft', 'theft attempt',
            # Fraud and security - Spanish
            'fraude', 'sospechoso', 'bloqueado', 'intento', 'acceso no autorizado',
            'robo', 'hurto',
        }
        
        # Security keywords (PT-BR + EN + ES)
        self.security_keywords = {
            # Authentication - Portuguese
            'senha', 'código', 'autenticação', 'verificação', 'verificar',
            'confirmar', 'confirmação', 'token', '2fa', 'otp',
            # Authentication - English
            'password', 'code', 'authentication', 'verification', 'verify',
            'confirm', 'confirmation', 'token', '2fa', 'otp',
            # Authentication - Spanish
            'contraseña', 'código', 'autenticación', 'verificación', 'verificar',
            'confirmar', 'confirmación', 'token', '2fa',
            
            # Alerts - Portuguese (specific, not generic)
            'alerta', 'aviso', 'emergência', 'urgente', 'crítico',
            'atenção', 'ação requerida', 'ação necessária', 'risco',
            # Alerts - English (specific, not generic)
            'alert', 'warning', 'emergency', 'urgent', 'critical',
            'attention', 'action required', 'risk', 'immediately',
            # Alerts - Spanish (specific, not generic)
            'alerta', 'advertencia', 'emergencia', 'urgente', 'crítico',
            'atención', 'acción requerida', 'riesgo',
            
            # Expiration - Portuguese (only specific keywords, not generic "válido")
            'expira', 'expiração', 'prazo', 'prazo limite',
            # Expiration - English
            'expires', 'expiration', 'deadline', 'time limit',
            # Expiration - Spanish
            'expira', 'expiración', 'plazo', 'límite de tiempo',
        }
        
        # Marketing/Newsletter keywords (PT-BR + EN + ES)
        self.marketing_keywords = {
            # Promotions - Portuguese (strong marketing signals)
            'promoção', 'oferta', 'desconto', 'newsletter',
            'campanha', 'anúncio', 'não perca', 'black friday',
            'cyber monday', 'liquidação', 'cupom', 'voucher', 'grátis', 'ganhe',
            'sorteio', 'concurso', 'cancelar inscrição', 'sair da lista',
            # Promotions - English
            'promotion', 'offer', 'discount', 'newsletter',
            'campaign', 'advertisement', "don't miss", 'black friday',
            'cyber monday', 'sale', 'coupon', 'voucher', 'free', 'win', 'raffle',
            'contest', 'unsubscribe', 'leave list',
            # Promotions - Spanish
            'promoción', 'oferta', 'descuento', 'boletín',
            'campaña', 'anuncio', 'no pierda', 'viernes negro',
            'cyber lunes', 'liquidación', 'cupón', 'bono', 'gratis', 'gane',
            'sorteo', 'concurso', 'cancelar suscripción', 'salir de la lista',
            
            # Engagement - Portuguese (specific to newsletters/marketing)
            'clique aqui', 'saiba mais', 'conheça', 'exclusivo', 'limitado',
            'apenas hoje', 'enquanto durar', 'acesse agora',
            # Engagement - English
            'click here', 'learn more', 'exclusive', 'limited',
            'today only', 'while stocks last', 'access now',
            # Engagement - Spanish
            'haz clic aquí', 'aprende más', 'exclusivo', 'limitado',
            'solo hoy', 'mientras exista', 'accede ahora',
        }
        
        # Compile regex patterns for better performance
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile regex patterns for efficient matching (multi-language support)."""
        # Financial patterns (PT-BR, EN, ES)
        self.financial_patterns: List[Pattern] = [
            # Currency amounts: R$, $, €, £, ¥, etc
            re.compile(r'[R$€£¥¢₹₽]\s*[\d.,]+', re.IGNORECASE),
            re.compile(r'[\d.,]+\s*(?:reais|dólares|euros|pesos|euros)', re.IGNORECASE),
            # Card numbers (generic pattern)
            re.compile(r'\b\d{4}\s*\d{4}\s*\d{4}\s*\d{4}\b'),
            # PIX, transferencia, pago - PT-BR
            re.compile(r'\bPIX\b', re.IGNORECASE),
            re.compile(r'\b(?:transferência|transfer|pago|pagamento)\s+(?:de|no valor|de\s*r\$)', re.IGNORECASE),
            re.compile(r'\b(?:fatura|boleto|factura)\s+(?:vence|vencida)', re.IGNORECASE),
            # EN patterns
            re.compile(r'\b(?:transfer|payment|invoice)\s+(?:of|in|amount)', re.IGNORECASE),
            re.compile(r'\b(?:bill|receipt|balance)\s+(?:due|updated)', re.IGNORECASE),
            # ES patterns
            re.compile(r'\b(?:transferencia|pago|factura)\s+(?:de|en|cantidad)', re.IGNORECASE),
            re.compile(r'\b(?:recibo|saldo|cobro)\s+(?:vencido|actualizado)', re.IGNORECASE),
        ]
        
        # Security patterns (PT-BR, EN, ES)
        self.security_patterns: List[Pattern] = [
            # Numeric codes (OTP)
            re.compile(r'\b\d{4,8}\b'),
            # Token-like strings
            re.compile(r'\b[A-Z0-9]{6,}\b'),
            # Password/Token: X = Y pattern - PT-BR
            re.compile(r'(?:senha|código|token|pin)[:=\s]*[\'"]?\w+[\'"]?', re.IGNORECASE),
            # Password/Token pattern - EN
            re.compile(r'(?:password|code|token|pin)[:=\s]*[\'"]?\w+[\'"]?', re.IGNORECASE),
            # Password/Token pattern - ES
            re.compile(r'(?:contraseña|código|token|pin)[:=\s]*[\'"]?\w+[\'"]?', re.IGNORECASE),
            # Expiration patterns - PT-BR (only expira/vence, not generic "válido até")
            re.compile(r'\b(?:expira|vence)\s+(?:em|por|até|dentro)', re.IGNORECASE),
            # Expiration patterns - EN
            re.compile(r'\b(?:expires)\s+(?:in|by|on)', re.IGNORECASE),
            # Expiration patterns - ES
            re.compile(r'\b(?:expira|vence)\s+(?:en|por|hasta|dentro)', re.IGNORECASE),
            # Confirmation patterns - PT-BR (only for action verbs like "confirme sua senha")
            re.compile(r'\b(?:confirme|verifique|acesse)\s+(?:sua|seu|a|o)\s+(?:senha|código|conta)', re.IGNORECASE),
            # Confirmation patterns - EN
            re.compile(r'\b(?:confirm|verify|access)\s+(?:your|the)\s+(?:password|code|account)', re.IGNORECASE),
            # Confirmation patterns - ES
            re.compile(r'\b(?:confirma|verifica|accede)\s+(?:su|tu|el|la)\s+(?:contrase\u00f1a|c\u00f3digo|cuenta)', re.IGNORECASE),
        ]
        
        # Marketing patterns (PT-BR, EN, ES)
        self.marketing_patterns: List[Pattern] = [
            # Percentage discounts: 50% OFF, 50% DESCONTO, 50% DE DESCUENTO
            re.compile(r'\b\d+%\s*(?:OFF|DESC|DESCONTO|DESCUENTO|DE\s+DESC)', re.IGNORECASE),
            # "Up to 50%" pattern - PT-BR: "até 50%"
            re.compile(r'\b(?:até|por|com)\s+\d+%', re.IGNORECASE),
            # "Up to" patterns - EN
            re.compile(r'\b(?:up\s+to|save|get)\s+\d+%', re.IGNORECASE),
            # "Up to" patterns - ES
            re.compile(r'\b(?:hasta|ahorra|consigue)\s+\d+%', re.IGNORECASE),
            # Buy X get Y pattern - PT-BR
            re.compile(r'\bcompre\s+\d+\s+leve\s+\d+\b', re.IGNORECASE),
            # Buy X get Y pattern - EN
            re.compile(r'\bbuy\s+\d+\s+get\s+\d+\b', re.IGNORECASE),
            # Buy X get Y pattern - ES
            re.compile(r'\bcompra\s+\d+\s+lleva\s+\d+\b', re.IGNORECASE),
            # "Don't miss" / "Não perca" / "No pierdas"
            re.compile(r'\b(?:não perca|aproveite|don\'t miss|take advantage|no pierda|aprovecha)\b', re.IGNORECASE),
            # Limited time patterns
            re.compile(r'\b(?:apenas\s+hoje|today\s+only|solo\s+hoy|por\s+tempo|while\s+stocks|mientras)\b', re.IGNORECASE),
        ]
    
    def match_keywords(
        self,
        text: str,
        keyword_set: Set[str]
    ) -> List[str]:
        """Match keywords in text (case-insensitive)."""
        if not text:
            return []
        
        text_lower = text.lower()
        matched = []
        
        for keyword in keyword_set:
            if keyword.lower() in text_lower:
                matched.append(keyword)
        
        return matched
    
    def match_patterns(
        self,
        text: str,
        patterns: List[Pattern]
    ) -> List[str]:
        """Match regex patterns in text."""
        if not text:
            return []
        
        matched = []
        for pattern in patterns:
            matches = pattern.findall(text)
            if matches:
                matched.extend([str(m) for m in matches])
        
        return matched


class UrgencyRuleEngine:
    """Deterministic rule engine for urgency classification."""
    
    def __init__(self):
        self.matcher = KeywordMatcher()
        self._stats = {
            'total_evaluations': 0,
            'urgent_decisions': 0,
            'not_urgent_decisions': 0,
            'undecided': 0,
            'rules_triggered': {}
        }
    
    def evaluate(self, message: NormalizedMessage) -> RuleMatch:
        """
        Evaluate message urgency using deterministic rules.
        
        Rules are evaluated in priority order:
        1. Group messages (not urgent)
        2. Security keywords (urgent - highest priority)
        3. Financial keywords (urgent)
        4. Marketing keywords (not urgent)
        5. Unknown (undecided - needs LLM)
        
        Args:
            message: Normalized message to evaluate
            
        Returns:
            RuleMatch with decision and details
        """
        self._stats['total_evaluations'] += 1
        
        # Extract text content
        text = self._extract_text(message)
        
        # Handle both enum and string values for message_type
        message_type_str = message.message_type.value if hasattr(message.message_type, 'value') else str(message.message_type)
        
        logger.debug(
            f"Evaluating urgency for message: {message.message_id}",
            message_id=message.message_id,
            message_type=message_type_str,
            has_text=bool(text)
        )
        
        # Rule 1: Group messages are never urgent by default
        if message.metadata.is_group:
            return self._create_match(
                decision=UrgencyDecision.NOT_URGENT,
                rule_name="group_message",
                confidence=0.95,
                reasoning="Group messages are not urgent by default"
            )
        
        # Rule 2: Security keywords = urgent (check FIRST, highest priority)
        security_match = self._check_security(text)
        if security_match:
            return security_match
        
        # Rule 3: Financial keywords = urgent
        financial_match = self._check_financial(text)
        if financial_match:
            return financial_match
        
        # Rule 4: Marketing keywords = not urgent
        marketing_match = self._check_marketing(text)
        if marketing_match:
            return marketing_match
        
        # Rule 5: Empty or media-only messages
        if not text or len(text.strip()) < 10:
            return self._create_match(
                decision=UrgencyDecision.NOT_URGENT,
                rule_name="empty_or_short",
                confidence=0.7,
                reasoning="Empty or very short message"
            )
        
        # No rules matched - need LLM
        return self._create_match(
            decision=UrgencyDecision.UNDECIDED,
            rule_name="no_match",
            confidence=0.0,
            reasoning="No deterministic rules matched, LLM evaluation needed"
        )
    
    def _extract_text(self, message: NormalizedMessage) -> str:
        """Extract all text content from message."""
        parts = []
        
        # Main text
        if message.content.text:
            parts.append(message.content.text)
        
        # Caption (for media messages)
        if message.content.caption:
            parts.append(message.content.caption)
        
        return " ".join(parts)
    
    def _check_financial(self, text: str) -> Optional[RuleMatch]:
        """Check for financial keywords and patterns."""
        if not text:
            return None
        
        # Check keywords
        keyword_matches = self.matcher.match_keywords(
            text,
            self.matcher.financial_keywords
        )
        
        # Check patterns
        pattern_matches = self.matcher.match_patterns(
            text,
            self.matcher.financial_patterns
        )
        
        all_matches = keyword_matches + pattern_matches
        
        if all_matches:
            confidence = min(0.99, 0.85 + len(all_matches) * 0.05)
            return self._create_match(
                decision=UrgencyDecision.URGENT,
                rule_name="financial_content",
                confidence=confidence,
                matched_keywords=all_matches[:5],  # Limit to first 5
                reasoning=f"Financial keywords/patterns detected: {len(all_matches)} matches"
            )
        
        return None
    
    def _check_security(self, text: str) -> Optional[RuleMatch]:
        """Check for security keywords and patterns."""
        if not text:
            return None
        
        # Check keywords
        keyword_matches = self.matcher.match_keywords(
            text,
            self.matcher.security_keywords
        )
        
        # Check patterns
        pattern_matches = self.matcher.match_patterns(
            text,
            self.matcher.security_patterns
        )
        
        all_matches = keyword_matches + pattern_matches
        
        if all_matches:
            confidence = min(0.99, 0.80 + len(all_matches) * 0.05)
            return self._create_match(
                decision=UrgencyDecision.URGENT,
                rule_name="security_content",
                confidence=confidence,
                matched_keywords=all_matches[:5],
                reasoning=f"Security keywords/patterns detected: {len(all_matches)} matches"
            )
        
        return None
    
    def _check_marketing(self, text: str) -> Optional[RuleMatch]:
        """Check for marketing/newsletter keywords."""
        if not text:
            return None
        
        # Check keywords
        keyword_matches = self.matcher.match_keywords(
            text,
            self.matcher.marketing_keywords
        )
        
        # Check patterns
        pattern_matches = self.matcher.match_patterns(
            text,
            self.matcher.marketing_patterns
        )
        
        all_matches = keyword_matches + pattern_matches
        
        # Need at least 2 matches to be confident it's marketing
        if len(all_matches) >= 2:
            confidence = min(0.95, 0.75 + len(all_matches) * 0.05)
            return self._create_match(
                decision=UrgencyDecision.NOT_URGENT,
                rule_name="marketing_content",
                confidence=confidence,
                matched_keywords=all_matches[:5],
                reasoning=f"Marketing keywords/patterns detected: {len(all_matches)} matches"
            )
        
        return None
    
    def _create_match(
        self,
        decision: UrgencyDecision,
        rule_name: str,
        confidence: float,
        matched_keywords: List[str] = None,
        reasoning: str = ""
    ) -> RuleMatch:
        """Create a rule match and update stats."""
        # Update stats
        if decision == UrgencyDecision.URGENT:
            self._stats['urgent_decisions'] += 1
        elif decision == UrgencyDecision.NOT_URGENT:
            self._stats['not_urgent_decisions'] += 1
        else:
            self._stats['undecided'] += 1
        
        self._stats['rules_triggered'][rule_name] = \
            self._stats['rules_triggered'].get(rule_name, 0) + 1
        
        # Log decision
        logger.info(
            f"Rule engine decision: {decision.value}",
            decision=decision.value,
            rule_name=rule_name,
            confidence=confidence,
            matched_keywords=matched_keywords or []
        )
        
        return RuleMatch(
            decision=decision,
            rule_name=rule_name,
            confidence=confidence,
            matched_keywords=matched_keywords or [],
            reasoning=reasoning
        )
    
    def get_stats(self) -> Dict:
        """Get rule engine statistics."""
        total = self._stats['total_evaluations']
        if total == 0:
            return self._stats
        
        return {
            **self._stats,
            'urgent_percentage': (self._stats['urgent_decisions'] / total) * 100,
            'not_urgent_percentage': (self._stats['not_urgent_decisions'] / total) * 100,
            'undecided_percentage': (self._stats['undecided'] / total) * 100,
        }
    
    def reset_stats(self):
        """Reset statistics."""
        self._stats = {
            'total_evaluations': 0,
            'urgent_decisions': 0,
            'not_urgent_decisions': 0,
            'undecided': 0,
            'rules_triggered': {}
        }


# Global instance
_engine_instance: Optional[UrgencyRuleEngine] = None


def get_rule_engine() -> UrgencyRuleEngine:
    """Get or create global rule engine instance."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = UrgencyRuleEngine()
    return _engine_instance

