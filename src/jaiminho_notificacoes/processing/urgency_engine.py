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
    """Efficient keyword and pattern matching."""
    
    def __init__(self):
        # Financial keywords (Portuguese + English)
        self.financial_keywords = {
            # Banking
            'banco', 'bank', 'conta', 'account', 'saldo', 'balance',
            'transferência', 'transfer', 'pix', 'ted', 'doc',
            'cartão', 'card', 'crédito', 'credit', 'débito', 'debit',
            'fatura', 'invoice', 'boleto', 'pagamento', 'payment',
            
            # Transactions
            'transação', 'transaction', 'compra', 'purchase',
            'cobrança', 'charge', 'estorno', 'refund',
            'aprovado', 'approved', 'negado', 'denied',
            'pendente', 'pending',
            
            # Amounts and currency
            'r$', 'brl', 'usd', 'euro', '€', '$',
            
            # Fraud and security
            'fraude', 'fraud', 'suspeito', 'suspicious',
            'bloqueio', 'blocked', 'bloqueado',
            'tentativa', 'attempt', 'acesso não autorizado',
            'unauthorized access',
        }
        
        # Security keywords
        self.security_keywords = {
            'senha', 'password', 'token', 'código', 'code',
            'autenticação', 'authentication', '2fa', 'otp',
            'verificação', 'verification', 'verificar', 'verify',
            'confirmar', 'confirm', 'confirmação', 'confirmation',
            'alerta', 'alert', 'aviso', 'warning',
            'emergência', 'emergency', 'urgente', 'urgent',
            'crítico', 'critical', 'importante', 'important',
            'atenção', 'attention', 'ação requerida', 'action required',
            'expira', 'expires', 'expiração', 'expiration',
        }
        
        # Marketing/Newsletter keywords
        self.marketing_keywords = {
            'promoção', 'promotion', 'oferta', 'offer', 'desconto', 'discount',
            'novidade', 'news', 'lançamento', 'launch', 'newsletter',
            'campanha', 'campaign', 'anúncio', 'advertisement',
            'aproveite', 'take advantage', 'não perca', "don't miss",
            'black friday', 'cyber monday', 'liquidação', 'sale',
            'cupom', 'coupon', 'voucher', 'grátis', 'free',
            'ganhe', 'win', 'sorteio', 'raffle', 'concurso', 'contest',
            'cancelar inscrição', 'unsubscribe', 'sair da lista',
        }
        
        # Compile regex patterns for better performance
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile regex patterns for efficient matching."""
        # Financial patterns
        self.financial_patterns: List[Pattern] = [
            re.compile(r'R\$\s*[\d.,]+', re.IGNORECASE),  # Currency amounts
            re.compile(r'\b\d{4}\s*\d{4}\s*\d{4}\s*\d{4}\b'),  # Card numbers
            re.compile(r'\bPIX\b', re.IGNORECASE),
            re.compile(r'\b(?:transferência|pagamento)\s+(?:de|no valor)', re.IGNORECASE),
            re.compile(r'\b(?:fatura|boleto)\s+vence', re.IGNORECASE),
        ]
        
        # Security patterns
        self.security_patterns: List[Pattern] = [
            re.compile(r'\b\d{4,6}\b'),  # Numeric codes (OTP)
            re.compile(r'\b[A-Z0-9]{6,}\b'),  # Token-like strings
            re.compile(r'(?:senha|token|código)[:=\s]+\w+', re.IGNORECASE),
            re.compile(r'\b(?:expira|válido)\s+(?:em|por|até)', re.IGNORECASE),
            re.compile(r'\b(?:confirme|verifique)\s+(?:sua|seu|a|o)', re.IGNORECASE),
        ]
        
        # Marketing patterns
        self.marketing_patterns: List[Pattern] = [
            re.compile(r'\b\d+%\s*(?:OFF|DESCONTO)', re.IGNORECASE),
            re.compile(r'\b(?:até|com)\s+\d+%', re.IGNORECASE),
            re.compile(r'\b(?:aproveite|não perca)', re.IGNORECASE),
            re.compile(r'\bcompre\s+\d+\s+leve\s+\d+\b', re.IGNORECASE),
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
        2. Financial/Security (urgent)
        3. Marketing (not urgent)
        4. Unknown (undecided - needs LLM)
        
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
        
        # Rule 2: Financial keywords = urgent
        financial_match = self._check_financial(text)
        if financial_match:
            return financial_match
        
        # Rule 3: Marketing keywords = not urgent (check before security to avoid false positives)
        marketing_match = self._check_marketing(text)
        if marketing_match:
            return marketing_match
        
        # Rule 4: Security keywords = urgent
        security_match = self._check_security(text)
        if security_match:
            return security_match
        
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

