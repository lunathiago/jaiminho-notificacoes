"""LLM-based agents for message processing decisions."""

import json
import os
from typing import Tuple, Dict, List, Optional
from abc import ABC, abstractmethod
from dataclasses import dataclass

from jaiminho_notificacoes.processing.urgency_engine import UrgencyDecision
from jaiminho_notificacoes.core.logger import TenantContextLogger
from jaiminho_notificacoes.persistence.models import NormalizedMessage


logger = TenantContextLogger(__name__)


@dataclass
class UrgencyResult:
    """Structured result from urgency analysis."""
    urgent: bool
    reason: str
    confidence: float  # 0.0 to 1.0
    
    def to_json(self) -> Dict:
        """Convert to JSON-serializable dict."""
        return {
            "urgent": self.urgent,
            "reason": self.reason,
            "confidence": round(self.confidence, 3)
        }


@dataclass
class HistoricalInterruptionData:
    """Historical data about user's interruption patterns."""
    sender_phone: str
    total_messages: int = 0
    urgent_count: int = 0
    not_urgent_count: int = 0
    avg_response_time_seconds: Optional[float] = None
    last_urgent_timestamp: Optional[int] = None
    user_feedback_count: int = 0  # Times user marked as urgent/not urgent
    
    @property
    def urgency_rate(self) -> float:
        """Percentage of messages from this sender marked as urgent."""
        total = self.urgent_count + self.not_urgent_count
        return (self.urgent_count / total) if total > 0 else 0.0


class BaseAgent(ABC):
    """Base class for LLM agents."""
    
    def __init__(self, model: str = "gpt-4"):
        """Initialize agent."""
        self.model = model
        self.api_key = os.getenv("OPENAI_API_KEY")
    
    @abstractmethod
    async def run(self, **kwargs) -> dict:
        """Run agent."""
        pass


class UrgencyAgent(BaseAgent):
    """
    LLM Agent for urgency classification.
    
    Decides whether a message is important enough to interrupt the user immediately.
    Conservative by default - when in doubt, do not interrupt.
    
    Inputs:
    - Message content
    - Sender phone number
    - Chat context (group or private)
    - Historical interruption data (same user only)
    
    Output:
    {
        urgent: boolean,
        reason: string,
        confidence: float (0.0 to 1.0)
    }
    """
    
    # Conservative thresholds
    CONFIDENCE_THRESHOLD_URGENT = 0.75  # Must be very confident to interrupt
    CONFIDENCE_THRESHOLD_KNOWN_SENDER = 0.65  # Slightly lower for known senders
    
    async def run(
        self,
        message: NormalizedMessage,
        historical_data: Optional[HistoricalInterruptionData] = None,
        context: str = ""
    ) -> UrgencyResult:
        """
        Classify message urgency using LLM with historical context.
        
        Args:
            message: The normalized message to classify
            historical_data: Historical interruption data for this sender
            context: Additional context (e.g., recent conversation)
        
        Returns:
            UrgencyResult with decision, reason, and confidence
        """
        logger.debug(
            "Running urgency agent",
            sender=message.sender_phone,
            has_history=historical_data is not None
        )
        
        try:
            # Extract text
            text = message.content.text or message.content.caption or ""
            
            # Quick rejection for empty messages
            if not text or len(text.strip()) < 5:
                return UrgencyResult(
                    urgent=False,
                    reason="Mensagem vazia ou muito curta para ser urgente",
                    confidence=0.85
                )
            
            # Quick rejection for group messages (conservative default)
            if message.metadata.is_group:
                return UrgencyResult(
                    urgent=False,
                    reason="Mensagens de grupo não são consideradas urgentes por padrão",
                    confidence=0.90
                )
            
            # Fetch historical data if not provided
            if historical_data is None:
                historical_data = await self._fetch_historical_data(
                    message.tenant_id,
                    message.user_id,
                    message.sender_phone
                )
            
            # Build prompt with historical context
            prompt = self._build_urgency_prompt(message, text, historical_data, context)
            
            # Call LLM
            response = await self._call_llm(prompt)
            
            # Parse response
            result = self._parse_urgency_response(response)
            
            # Apply conservative threshold
            result = self._apply_conservative_logic(result, historical_data, message)
            
            logger.info(
                "Urgency agent decision",
                urgent=result.urgent,
                confidence=result.confidence,
                sender=message.sender_phone
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Urgency agent error: {e}")
            # Conservative fallback - never interrupt on error
            return UrgencyResult(
                urgent=False,
                reason=f"Erro na análise: {str(e)}. Por segurança, não interromper.",
                confidence=0.5
            )
    
    async def _fetch_historical_data(
        self,
        tenant_id: str,
        user_id: str,
        sender_phone: str
    ) -> HistoricalInterruptionData:
        """
        Fetch historical interruption data for this sender.
        
        In production, this would query DynamoDB for:
        - Past messages from this sender
        - User's feedback on urgency
        - Response times
        - Urgency patterns
        
        For now, returns empty data.
        """
        logger.debug(
            "Fetching historical data",
            tenant_id=tenant_id,
            user_id=user_id,
            sender_phone=sender_phone
        )
        
        # TODO: Implement DynamoDB query
        # Example query:
        # - Table: UserMessageHistory
        # - PK: user_id#sender_phone
        # - Query last N messages and urgency decisions
        
        return HistoricalInterruptionData(sender_phone=sender_phone)
    
    def _build_urgency_prompt(
        self,
        message: NormalizedMessage,
        text: str,
        historical_data: HistoricalInterruptionData,
        context: str
    ) -> str:
        """Build prompt for urgency classification with historical context."""
        
        message_type = message.message_type.value if hasattr(message.message_type, 'value') else str(message.message_type)
        
        # Build historical context section
        history_section = "DADOS HISTÓRICOS:\n"
        if historical_data and historical_data.total_messages > 0:
            history_section += f"- Total de mensagens deste remetente: {historical_data.total_messages}\n"
            history_section += f"- Taxa de urgência histórica: {historical_data.urgency_rate:.1%}\n"
            history_section += f"- Mensagens marcadas como urgentes: {historical_data.urgent_count}\n"
            history_section += f"- Mensagens marcadas como não urgentes: {historical_data.not_urgent_count}\n"
            
            if historical_data.avg_response_time_seconds:
                history_section += f"- Tempo médio de resposta: {historical_data.avg_response_time_seconds/60:.1f} minutos\n"
            
            if historical_data.last_urgent_timestamp:
                import time
                seconds_ago = int(time.time()) - historical_data.last_urgent_timestamp
                hours_ago = seconds_ago / 3600
                history_section += f"- Última mensagem urgente: há {hours_ago:.1f} horas\n"
        else:
            history_section += "- Nenhum histórico disponível para este remetente (primeiro contato ou dados insuficientes)\n"
        
        prompt = f"""Você é um assistente especializado em análise de urgência de mensagens para um sistema brasileiro de notificações do WhatsApp.

Sua tarefa é decidir se esta mensagem é importante o suficiente para INTERROMPER o usuário imediatamente.

SEJA CONSERVADOR: Em caso de dúvida, NÃO interrompa. Interromper é invasivo e deve ser reservado para situações genuinamente urgentes.

METADADOS DA MENSAGEM:
- Tipo: {message_type}
- Remetente: {message.sender_name or 'Desconhecido'} ({message.sender_phone})
- É grupo: {message.metadata.is_group}
- Encaminhada: {message.metadata.forwarded}
- Timestamp: {message.timestamp}

{history_section}

CONTEÚDO DA MENSAGEM (primeiros 800 caracteres):
{text[:800]}

CONTEXTO ADICIONAL:
{context or "Nenhum contexto adicional disponível"}

CRITÉRIOS DE URGÊNCIA (seja rigoroso):
URGENTE (urgent: true) apenas se:
- Alertas financeiros CRÍTICOS (fraude, bloqueio, transação suspeita)
- Códigos de verificação/autenticação com prazo curto
- Emergências genuínas (saúde, segurança, problemas graves)
- Comunicação sensível ao tempo com consequências imediatas (ex: reunião em 15min)
- Confirmações que expiram rapidamente

NÃO URGENTE (urgent: false) para:
- Marketing, promoções, ofertas
- Mensagens informativas gerais
- Conversas casuais
- Confirmações de ações já realizadas
- Lembretes sem prazo imediato
- Mensagens de grupo (exceto emergências óbvias)
- Primeiro contato de remetente desconhecido (seja cauteloso)

CONSIDERE O HISTÓRICO:
- Se taxa de urgência histórica é baixa (<20%), seja mais conservador
- Se é primeiro contato, seja MUITO conservador
- Se usuário frequentemente ignora mensagens deste remetente, não interrompa

Responda APENAS com um objeto JSON válido (sem markdown, sem texto extra):
{{
  "urgent": true ou false,
  "reason": "<explicação clara e breve em português do Brasil>",
  "confidence": <float entre 0.0 e 1.0>,
  "keywords_detected": [<lista de palavras-chave relevantes encontradas>]
}}

Lembre-se: SEJA CONSERVADOR. Quando em dúvida, NÃO interrompa."""
        
        return prompt
    
    async def _call_llm(self, prompt: str) -> str:
        """Call LLM API."""
        # Placeholder - in production would call OpenAI, Claude, etc.
        
        if not self.api_key:
            logger.warning("OPENAI_API_KEY not set - using conservative fallback")
            return json.dumps({
                "urgent": False,
                "confidence": 0.4,
                "keywords_detected": [],
                "reason": "API não configurada - por segurança, não interromper"
            })
        
        try:
            # Example: using OpenAI API
            # import openai
            # openai.api_key = self.api_key
            # 
            # response = openai.ChatCompletion.create(
            #     model=self.model,
            #     messages=[{"role": "user", "content": prompt}],
            #     temperature=0.2,
            #     max_tokens=200
            # )
            # return response.choices[0].message.content
            
            # Mock response for development
            logger.debug("Using mock LLM response (development mode)")
            return json.dumps({
                "urgent": False,
                "confidence": 0.65,
                "keywords_detected": [],
                "reason": "Mensagem analisada - não requer interrupção imediata"
            })
            
        except Exception as e:
            logger.error(f"LLM API call failed: {e}")
            # Conservative fallback
            return json.dumps({
                "urgent": False,
                "confidence": 0.3,
                "keywords_detected": [],
                "reason": f"Erro na chamada da API: {str(e)} - não interromper por segurança"
            })
    
    def _parse_urgency_response(self, response: str) -> UrgencyResult:
        """Parse LLM response into structured result."""
        try:
            # Try to extract JSON if wrapped in markdown
            response = response.strip()
            if response.startswith("```"):
                # Remove markdown code blocks
                lines = response.split("\n")
                response = "\n".join([l for l in lines if not l.startswith("```")])
            
            data = json.loads(response)
            
            urgent = bool(data.get("urgent", False))
            confidence = float(data.get("confidence", 0.5))
            reason = str(data.get("reason", "Sem justificativa fornecida"))
            
            # Clamp confidence to [0, 1]
            confidence = max(0.0, min(1.0, confidence))
            
            return UrgencyResult(
                urgent=urgent,
                reason=reason,
                confidence=confidence
            )
            
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.error(f"Failed to parse LLM response: {e}")
            logger.debug(f"Raw response: {response}")
            # Conservative fallback
            return UrgencyResult(
                urgent=False,
                reason=f"Erro ao processar resposta da análise: {str(e)}",
                confidence=0.3
            )
    
    def _apply_conservative_logic(
        self,
        result: UrgencyResult,
        historical_data: Optional[HistoricalInterruptionData],
        message: NormalizedMessage
    ) -> UrgencyResult:
        """
        Apply conservative thresholds and business rules.
        
        This ensures we don't interrupt users unnecessarily even if LLM
        suggests urgency with moderate confidence.
        """
        
        # Rule 1: Never interrupt if confidence is too low
        if result.urgent and result.confidence < self.CONFIDENCE_THRESHOLD_URGENT:
            # Lower threshold for known senders with good history
            if historical_data and historical_data.total_messages >= 5:
                if result.confidence < self.CONFIDENCE_THRESHOLD_KNOWN_SENDER:
                    logger.info(
                        "Overriding urgent decision due to low confidence",
                        original_confidence=result.confidence,
                        threshold=self.CONFIDENCE_THRESHOLD_KNOWN_SENDER
                    )
                    return UrgencyResult(
                        urgent=False,
                        reason=f"Confiança insuficiente para interromper ({result.confidence:.2f}). " + result.reason,
                        confidence=result.confidence
                    )
            else:
                logger.info(
                    "Overriding urgent decision due to low confidence",
                    original_confidence=result.confidence,
                    threshold=self.CONFIDENCE_THRESHOLD_URGENT
                )
                return UrgencyResult(
                    urgent=False,
                    reason=f"Confiança insuficiente para interromper ({result.confidence:.2f}). " + result.reason,
                    confidence=result.confidence
                )
        
        # Rule 2: First contact from unknown sender - be very conservative
        if result.urgent and historical_data and historical_data.total_messages == 0:
            # Only interrupt first contact if confidence is very high (>0.85)
            if result.confidence < 0.85:
                logger.info(
                    "Overriding urgent decision for first contact",
                    sender=message.sender_phone
                )
                return UrgencyResult(
                    urgent=False,
                    reason=f"Primeiro contato deste remetente - por segurança, não interromper. {result.reason}",
                    confidence=result.confidence * 0.8  # Reduce confidence
                )
        
        # Rule 3: Sender with low historical urgency rate
        if result.urgent and historical_data and historical_data.total_messages >= 10:
            if historical_data.urgency_rate < 0.1:  # Less than 10% urgent
                # Be more conservative
                if result.confidence < 0.85:
                    logger.info(
                        "Overriding urgent decision due to low historical urgency rate",
                        urgency_rate=historical_data.urgency_rate
                    )
                    return UrgencyResult(
                        urgent=False,
                        reason=f"Histórico indica baixa urgência deste remetente ({historical_data.urgency_rate:.1%}). {result.reason}",
                        confidence=result.confidence * 0.85
                    )
        
        # Rule 4: Group messages - almost never interrupt
        if result.urgent and message.metadata.is_group:
            if result.confidence < 0.90:  # Very high bar for group messages
                logger.info("Overriding urgent decision for group message")
                return UrgencyResult(
                    urgent=False,
                    reason=f"Mensagem de grupo - requer confiança muito alta para interromper. {result.reason}",
                    confidence=result.confidence * 0.7
                )
        
        return result


class ClassificationAgent(BaseAgent):
    """
    LLM Agent for final message classification.
    
    Takes urgency decision and produces routing decision:
    - immediate: Send via SendPulse now
    - digest: Add to daily digest
    - spam: Filter out
    """
    
    async def run(
        self,
        message: NormalizedMessage,
        urgency_decision: UrgencyDecision,
        urgency_confidence: float
    ) -> Tuple[str, str]:
        """
        Classify message for routing.
        
        Args:
            message: The normalized message
            urgency_decision: Result from urgency classification
            urgency_confidence: Confidence of urgency decision
        
        Returns:
            (classification, reasoning)
        """
        logger.debug(
            "Running classification agent",
            urgency=urgency_decision.value,
            confidence=urgency_confidence
        )
        
        try:
            # Build prompt
            prompt = self._build_classification_prompt(
                message,
                urgency_decision,
                urgency_confidence
            )
            
            # Call LLM
            response = await self._call_llm(prompt)
            
            # Parse response
            classification, reasoning = self._parse_classification_response(response)
            
            logger.debug(
                "Classification agent result",
                classification=classification
            )
            
            return classification, reasoning
            
        except Exception as e:
            logger.error(f"Classification agent error: {e}")
            # Conservative fallback
            if urgency_decision == UrgencyDecision.URGENT:
                return "immediate", f"Agent error - conservative: {str(e)}"
            else:
                return "digest", f"Agent error - conservative: {str(e)}"
    
    def _build_classification_prompt(
        self,
        message: NormalizedMessage,
        urgency_decision: UrgencyDecision,
        urgency_confidence: float
    ) -> str:
        """Build prompt for classification."""
        text = message.content.text or message.content.caption or ""
        message_type = message.message_type.value if hasattr(message.message_type, 'value') else str(message.message_type)
        
        prompt = f"""You are a routing agent for a Brazilian WhatsApp notification system.

Based on the urgency assessment, determine how to route this message:

MESSAGE:
- Type: {message_type}
- Sender: {message.sender_name or message.sender_phone}
- Is Group: {message.metadata.is_group}
- Content (first 200 chars): {text[:200]}

URGENCY ASSESSMENT:
- Decision: {urgency_decision.value}
- Confidence: {urgency_confidence}

ROUTING OPTIONS:
1. "immediate" - Send to user immediately via SendPulse notification
2. "digest" - Add to daily digest email
3. "spam" - Filter out and discard

Rules:
- If urgency is URGENT + confidence > 0.8 → immediate
- If urgency is NOT_URGENT + confidence > 0.8 → digest
- If confidence < 0.6 → digest (safer default)
- If message is from group + not urgent → digest

Respond with ONLY a valid JSON object (no markdown):
{{
  "classification": "immediate" or "digest" or "spam",
  "reasoning": "<brief explanation in Portuguese>"
}}"""
        
        return prompt
    
    async def _call_llm(self, prompt: str) -> str:
        """Call LLM API."""
        # Placeholder
        if not self.api_key:
            logger.warning("OPENAI_API_KEY not set - using fallback")
            return '{"classification": "digest", "reasoning": "API não configurada"}'
        
        # Mock response
        return '{"classification": "digest", "reasoning": "Roteamento padrão"}'
    
    def _parse_classification_response(
        self,
        response: str
    ) -> Tuple[str, str]:
        """Parse LLM response."""
        try:
            data = json.loads(response)
            
            classification = data.get("classification", "digest").lower()
            valid_options = ["immediate", "digest", "spam"]
            
            if classification not in valid_options:
                classification = "digest"
            
            reasoning = data.get("reasoning", "No reasoning provided")
            
            return classification, reasoning
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse classification response: {e}")
            raise


# Singleton instances
_urgency_agent: UrgencyAgent | None = None
_classification_agent: ClassificationAgent | None = None


def get_urgency_agent() -> UrgencyAgent:
    """Get or create urgency agent instance."""
    global _urgency_agent
    if _urgency_agent is None:
        _urgency_agent = UrgencyAgent()
    return _urgency_agent


def get_classification_agent() -> ClassificationAgent:
    """Get or create classification agent instance."""
    global _classification_agent
    if _classification_agent is None:
        _classification_agent = ClassificationAgent()
    return _classification_agent
