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


@dataclass
class ClassificationResult:
    """Structured result from classification agent."""
    category: str  # Cognitive-friendly category
    summary: str  # Short summary for digest
    routing: str  # immediate, digest, spam
    reasoning: str
    confidence: float  # 0.0 to 1.0
    
    def to_json(self) -> Dict:
        """Convert to JSON-serializable dict."""
        return {
            "category": self.category,
            "summary": self.summary,
            "routing": self.routing,
            "reasoning": self.reasoning,
            "confidence": round(self.confidence, 3)
        }


class ClassificationAgent(BaseAgent):
    """
    LLM Agent for message classification with cognitive-friendly categories.
    
    Capabilities:
    - Assigns cognitive-friendly categories (not technical labels)
    - Generates short summaries (1-2 sentences) for daily digest
    - Produces final routing decision (immediate, digest, spam)
    - NEVER uses cross-user data - only single-message context
    
    Categories (cognitive-friendly examples):
    - "💼 Trabalho e Negócios"
    - "👨‍👩‍👧 Família e Amigos"
    - "📦 Entregas e Compras"
    - "💰 Financeiro"
    - "🏥 Saúde"
    - "🎉 Eventos e Convites"
    - "📰 Informação Geral"
    - "🤖 Automação e Bots"
    - "❓ Outros"
    """
    
    # Cognitive-friendly categories with emojis for better recognition
    CATEGORIES = [
        "💼 Trabalho e Negócios",
        "👨‍👩‍👧 Família e Amigos",
        "📦 Entregas e Compras",
        "💰 Financeiro",
        "🏥 Saúde",
        "🎉 Eventos e Convites",
        "📰 Informação Geral",
        "🤖 Automação e Bots",
        "❓ Outros"
    ]
    
    async def run(
        self,
        message: NormalizedMessage,
        urgency_decision: UrgencyDecision,
        urgency_confidence: float,
        tenant_context: Optional[Dict] = None
    ) -> ClassificationResult:
        """
        Classify message with cognitive-friendly category and summary.
        
        Args:
            message: The normalized message (single-tenant, single-user only)
            urgency_decision: Result from urgency classification
            urgency_confidence: Confidence of urgency decision
            tenant_context: Optional tenant-specific settings (NOT cross-user data)
        
        Returns:
            ClassificationResult with category, summary, routing, and reasoning
        
        Security Note:
            This agent NEVER receives or uses data from other users.
            Only single-message context and optional tenant settings are used.
        """
        logger.debug(
            "Running classification agent",
            tenant_id=message.tenant_id,
            user_id=message.user_id,
            urgency=urgency_decision.value,
            confidence=urgency_confidence
        )
        
        # Validate tenant isolation - ensure message belongs to single tenant
        self._validate_tenant_isolation(message)
        
        try:
            # Build prompt (single-message context only)
            prompt = self._build_classification_prompt(
                message,
                urgency_decision,
                urgency_confidence
            )
            
            # Call LLM
            response = await self._call_llm(prompt)
            
            # Parse response
            result = self._parse_classification_response(response)
            
            # Apply routing logic
            result = self._apply_routing_logic(result, urgency_decision, urgency_confidence)
            
            logger.info(
                "Classification agent result",
                tenant_id=message.tenant_id,
                user_id=message.user_id,
                category=result.category,
                routing=result.routing
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Classification agent error: {e}", tenant_id=message.tenant_id)
            # Conservative fallback
            return self._create_fallback_result(urgency_decision, str(e))
    
    def _validate_tenant_isolation(self, message: NormalizedMessage):
        """
        Validate that message contains proper tenant isolation.
        
        Raises:
            ValueError: If tenant_id or user_id is missing
        """
        if not message.tenant_id or not message.user_id:
            raise ValueError(
                "ClassificationAgent requires tenant_id and user_id for proper isolation. "
                "Cannot process messages without tenant context."
            )
        
        logger.debug(
            "Tenant isolation validated",
            tenant_id=message.tenant_id,
            user_id=message.user_id
        )
    
    def _build_classification_prompt(
        self,
        message: NormalizedMessage,
        urgency_decision: UrgencyDecision,
        urgency_confidence: float
    ) -> str:
        """
        Build prompt for classification with cognitive categories.
        
        This prompt:
        - Uses single-message context only (no cross-user data)
        - Requests cognitive-friendly categories
        - Asks for short summaries suitable for digest
        - Guides routing decision
        """
        text = message.content.text or message.content.caption or ""
        message_type = message.message_type.value if hasattr(message.message_type, 'value') else str(message.message_type)
        
        categories_list = "\n".join([f"- {cat}" for cat in self.CATEGORIES])
        
        prompt = f"""Você é um assistente de classificação de mensagens para um sistema brasileiro de notificações do WhatsApp.

Sua tarefa é:
1. Atribuir uma CATEGORIA COGNITIVA amigável à mensagem
2. Gerar um RESUMO curto (1-2 frases) para o digest diário
3. Decidir o ROTEAMENTO (immediate, digest, spam)

IMPORTANTE - ISOLAMENTO DE DADOS:
- Use APENAS o contexto desta mensagem única
- NUNCA use ou solicite dados de outros usuários
- NUNCA compare com padrões de outros usuários
- Esta análise é específica para UM usuário e UMA mensagem

METADADOS DA MENSAGEM:
- Tipo: {message_type}
- Remetente: {message.sender_name or 'Desconhecido'} ({message.sender_phone})
- É grupo: {message.metadata.is_group}
- Grupo: {message.metadata.group_id or 'N/A'}
- Timestamp: {message.timestamp}

CONTEÚDO DA MENSAGEM (primeiros 500 caracteres):
{text[:500]}

AVALIAÇÃO DE URGÊNCIA (já feita):
- Decisão: {urgency_decision.value}
- Confiança: {urgency_confidence:.2f}

---

CATEGORIAS DISPONÍVEIS (escolha UMA):
{categories_list}

INSTRUÇÕES PARA RESUMO:
- 1-2 frases curtas (máximo 100 caracteres)
- Capture a ESSÊNCIA da mensagem
- Use linguagem natural e objetiva
- Seja útil para um digest diário
- Exemplos:
  * "João confirmou a reunião de amanhã às 14h"
  * "Sua encomenda foi enviada e chega em 2 dias"
  * "Mensagem de grupo sobre churrasco no sábado"

INSTRUÇÕES PARA ROTEAMENTO:
- "immediate": Se urgente E confiança > 0.75
- "digest": Para mensagens importantes mas não urgentes
- "spam": Para mensagens claramente promocionais/spam
- Em caso de dúvida, prefira "digest"

Responda com APENAS um objeto JSON válido (sem markdown):
{{
  "category": "<uma das categorias listadas acima>",
  "summary": "<resumo curto em português, 1-2 frases>",
  "routing": "immediate" ou "digest" ou "spam",
  "reasoning": "<breve explicação das escolhas>",
  "confidence": <número entre 0.0 e 1.0>
}}"""
        
        return prompt
    
    async def _call_llm(self, prompt: str) -> str:
        """
        Call LLM API for classification.
        
        Note: In production, this would use OpenAI or similar.
        For now, uses an intelligent fallback that analyzes the prompt content.
        """
        if not self.api_key:
            logger.warning("OPENAI_API_KEY not set - using intelligent fallback")
            
            # Extract message info from prompt for intelligent fallback
            # This is a temporary solution until LLM API is configured
            import re
            
            # Extract content from prompt
            content_match = re.search(r'CONTEÚDO DA MENSAGEM.*?:\n(.+?)(?:\n\n|$)', prompt, re.DOTALL)
            content = content_match.group(1) if content_match else ""
            content_lower = content.lower()
            
            # Classify category based on keywords
            category = "❓ Outros"
            if any(kw in content_lower for kw in ["trabalho", "reunião", "meeting", "projeto", "prazo", "deadline", "contrato"]):
                category = "💼 Trabalho e Negócios"
            elif any(kw in content_lower for kw in ["família", "mãe", "pai", "filho", "amigo", "querido"]):
                category = "👨‍👩‍👧 Família e Amigos"
            elif any(kw in content_lower for kw in ["entrega", "pedido", "compra", "rastreio", "correios", "sedex"]):
                category = "📦 Entregas e Compras"
            elif any(kw in content_lower for kw in ["pagamento", "boleto", "fatura", "pix", "transferência", "banco"]):
                category = "💰 Financeiro"
            elif any(kw in content_lower for kw in ["médico", "consulta", "exame", "saúde", "hospital", "remédio"]):
                category = "🏥 Saúde"
            elif any(kw in content_lower for kw in ["evento", "festa", "convite", "aniversário", "celebração"]):
                category = "🎉 Eventos e Convites"
            elif any(kw in content_lower for kw in ["bot", "automático", "notificação", "alerta", "sistema"]):
                category = "🤖 Automação e Bots"
            else:
                category = "📰 Informação Geral"
            
            # Extract sender name
            sender_match = re.search(r'Remetente: (.+?) \(', prompt)
            sender_name = sender_match.group(1) if sender_match else "Contato"
            
            # Generate summary
            summary_text = content[:80].strip()
            if len(content) > 80:
                summary_text += "..."
            summary = f"{sender_name}: {summary_text}"
            
            # Determine routing based on urgency in prompt
            routing = "digest"
            if "URGENT" in prompt or "urgente" in content_lower:
                routing = "digest"  # Will be overridden by routing logic if needed
            
            return f'''{{
                "category": "{category}",
                "summary": "{summary}",
                "routing": "{routing}",
                "reasoning": "Classificação baseada em análise de palavras-chave (API não configurada)",
                "confidence": 0.7
            }}'''
        
        # TODO: Implement actual OpenAI API call
        # Example:
        # import openai
        # response = await openai.ChatCompletion.acreate(
        #     model=self.model,
        #     messages=[{"role": "user", "content": prompt}],
        #     temperature=0.3,
        #     max_tokens=200
        # )
        # return response.choices[0].message.content
        
        # Mock response for development
        return '''{
            "category": "📰 Informação Geral",
            "summary": "Nova mensagem recebida",
            "routing": "digest",
            "reasoning": "Classificação padrão",
            "confidence": 0.7
        }'''
    
    def _parse_classification_response(self, response: str) -> ClassificationResult:
        """
        Parse LLM response into ClassificationResult.
        
        Args:
            response: JSON string from LLM
        
        Returns:
            ClassificationResult
        
        Raises:
            ValueError: If response is invalid
        """
        try:
            data = json.loads(response)
            
            # Extract and validate fields
            category = data.get("category", "❓ Outros")
            if category not in self.CATEGORIES:
                logger.warning(f"Invalid category '{category}', using default")
                category = "❓ Outros"
            
            summary = data.get("summary", "Mensagem sem resumo")
            # Truncate summary if too long
            if len(summary) > 150:
                summary = summary[:147] + "..."
            
            routing = data.get("routing", "digest").lower()
            valid_routing = ["immediate", "digest", "spam"]
            if routing not in valid_routing:
                logger.warning(f"Invalid routing '{routing}', using 'digest'")
                routing = "digest"
            
            reasoning = data.get("reasoning", "Sem justificativa")
            confidence = float(data.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))  # Clamp to [0, 1]
            
            return ClassificationResult(
                category=category,
                summary=summary,
                routing=routing,
                reasoning=reasoning,
                confidence=confidence
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse classification response: {e}")
            raise ValueError(f"Invalid JSON response from LLM: {e}")
        except Exception as e:
            logger.error(f"Error parsing classification response: {e}")
            raise
    
    def _apply_routing_logic(
        self,
        result: ClassificationResult,
        urgency_decision: UrgencyDecision,
        urgency_confidence: float
    ) -> ClassificationResult:
        """
        Apply business rules to routing decision.
        
        This ensures routing aligns with urgency assessment and
        applies conservative logic.
        """
        original_routing = result.routing
        
        # Rule 1: High-confidence urgent → immediate
        if urgency_decision == UrgencyDecision.URGENT and urgency_confidence > 0.75:
            if result.routing != "immediate":
                logger.info(
                    "Overriding routing to immediate based on high-confidence urgency",
                    original=original_routing,
                    urgency_confidence=urgency_confidence
                )
                result.routing = "immediate"
                result.reasoning += " [Roteamento ajustado: alta urgência detectada]"
        
        # Rule 2: Low urgency confidence → default to digest
        elif urgency_confidence < 0.5:
            if result.routing == "immediate":
                logger.info(
                    "Overriding immediate routing due to low urgency confidence",
                    urgency_confidence=urgency_confidence
                )
                result.routing = "digest"
                result.reasoning += " [Roteamento ajustado: baixa confiança]"
        
        # Rule 3: NOT_URGENT with high confidence → never immediate
        elif urgency_decision == UrgencyDecision.NOT_URGENT and urgency_confidence > 0.7:
            if result.routing == "immediate":
                logger.info(
                    "Overriding immediate routing - message classified as not urgent",
                    urgency_confidence=urgency_confidence
                )
                result.routing = "digest"
                result.reasoning += " [Roteamento ajustado: mensagem não urgente]"
        
        return result
    
    def _create_fallback_result(
        self,
        urgency_decision: UrgencyDecision,
        error_msg: str
    ) -> ClassificationResult:
        """
        Create conservative fallback result in case of errors.
        
        Args:
            urgency_decision: Original urgency decision
            error_msg: Error message
        
        Returns:
            Safe fallback ClassificationResult
        """
        # Conservative routing: only immediate if urgent, otherwise digest
        routing = "immediate" if urgency_decision == UrgencyDecision.URGENT else "digest"
        
        return ClassificationResult(
            category="❓ Outros",
            summary="Erro no processamento - mensagem preservada para digest",
            routing=routing,
            reasoning=f"Fallback devido a erro: {error_msg}",
            confidence=0.5
        )


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
