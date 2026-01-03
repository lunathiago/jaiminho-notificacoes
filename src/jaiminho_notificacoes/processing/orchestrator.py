"""LangGraph orchestration for message processing workflows."""

import json
from typing import TypedDict, Optional, Literal
from datetime import datetime
from dataclasses import asdict

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

from jaiminho_notificacoes.persistence.models import (
    NormalizedMessage,
    ProcessingDecision,
    ProcessingResult
)
from jaiminho_notificacoes.processing.urgency_engine import (
    UrgencyRuleEngine,
    UrgencyDecision,
    get_rule_engine
)
from jaiminho_notificacoes.processing.agents import (
    get_urgency_agent,
    get_classification_agent,
    ClassificationResult
)
from jaiminho_notificacoes.core.logger import TenantContextLogger
from jaiminho_notificacoes.core.tenant import TenantResolver


logger = TenantContextLogger(__name__)


class ProcessingState(TypedDict):
    """State for message processing workflow."""
    
    # Input
    message: NormalizedMessage
    
    # Rule Engine Results
    rule_decision: Optional[UrgencyDecision]
    rule_confidence: float
    rule_matched_keywords: list[str]
    rule_reasoning: str
    
    # Agent Decisions
    urgency_agent_decision: Optional[UrgencyDecision]
    urgency_agent_reasoning: str
    urgency_agent_confidence: float
    
    # Classification Agent Results (with categories and summaries)
    classification_result: Optional[ClassificationResult]
    classification_category: str
    classification_summary: str
    classification_routing: Literal["immediate", "digest", "spam"]
    classification_reasoning: str
    
    # Final Decision
    final_decision: Literal["immediate", "digest", "spam"]
    audit_trail: list[dict]


class MessageProcessingOrchestrator:
    """
    LangGraph-based orchestrator for message processing.
    
    Flow:
    1. Rule Engine → deterministic classification
    2. If UNDECIDED → Urgency Agent (LLM)
    3. Classification Agent → final routing decision
    4. Router → SendPulse or persistence
    """
    
    def __init__(self):
        """Initialize orchestrator with LangGraph."""
        self.rule_engine: UrgencyRuleEngine = get_rule_engine()
        self.tenant_resolver = TenantResolver()
        self._build_graph()
    
    def _build_graph(self):
        """Build LangGraph state machine."""
        graph = StateGraph(ProcessingState)
        
        # Add nodes
        graph.add_node("rule_engine", self._node_rule_engine)
        graph.add_node("urgency_agent", self._node_urgency_agent)
        graph.add_node("classification_agent", self._node_classification_agent)
        graph.add_node("route_decision", self._node_route_decision)
        graph.add_node("audit_log", self._node_audit_log)
        
        # Set entry point
        graph.set_entry_point("rule_engine")
        
        # Add edges
        graph.add_edge("rule_engine", "urgency_agent")
        graph.add_edge("urgency_agent", "classification_agent")
        graph.add_edge("classification_agent", "route_decision")
        graph.add_edge("route_decision", "audit_log")
        graph.add_edge("audit_log", END)
        
        self.graph = graph.compile()
    
    async def process(self, message: NormalizedMessage) -> ProcessingResult:
        """Process message through the orchestration flow."""
        logger.set_context(
            tenant_id=message.tenant_id,
            user_id=message.user_id,
            message_id=message.message_id
        )
        
        try:
            # Initialize state
            initial_state: ProcessingState = {
                "message": message,
                "rule_decision": None,
                "rule_confidence": 0.0,
                "rule_matched_keywords": [],
                "rule_reasoning": "",
                "urgency_agent_decision": None,
                "urgency_agent_reasoning": "",
                "urgency_agent_confidence": 0.0,
                "classification_result": None,
                "classification_category": "",
                "classification_summary": "",
                "classification_routing": "digest",
                "classification_reasoning": "",
                "final_decision": "digest",
                "audit_trail": [],
            }
            
            # Execute graph
            final_state = await self.graph.ainvoke(initial_state)
            
            # Create result
            result = ProcessingResult(
                message_id=message.message_id,
                tenant_id=message.tenant_id,
                user_id=message.user_id,
                decision=ProcessingDecision(final_state["final_decision"]),
                rule_engine_decision=final_state["rule_decision"],
                rule_confidence=final_state["rule_confidence"],
                llm_used=(final_state["rule_decision"] == UrgencyDecision.UNDECIDED),
                audit_trail=final_state["audit_trail"],
                processed_at=datetime.utcnow().isoformat()
            )
            
            logger.info(
                "Message processing completed",
                decision=result.decision.value,
                rule_decision=final_state["rule_decision"].value if final_state["rule_decision"] else None,
                llm_used=result.llm_used,
            )
            
            return result
            
        except Exception as e:
            logger.error(
                "Error in message processing orchestration",
                error=str(e),
                error_type=type(e).__name__
            )
            raise
        finally:
            logger.clear_context()
    
    def _node_rule_engine(self, state: ProcessingState) -> ProcessingState:
        """Node: Execute deterministic rule engine."""
        message = state["message"]
        
        # Evaluate with rule engine
        rule_result = self.rule_engine.evaluate(message)
        
        # Update state
        state["rule_decision"] = rule_result.decision
        state["rule_confidence"] = rule_result.confidence
        state["rule_matched_keywords"] = rule_result.matched_keywords
        state["rule_reasoning"] = rule_result.reasoning
        
        # Log
        logger.debug(
            "Rule engine evaluation",
            decision=rule_result.decision.value,
            confidence=rule_result.confidence,
            rule=rule_result.rule_name,
            keyword_count=len(rule_result.matched_keywords)
        )
        
        # Audit
        state["audit_trail"].append({
            "step": "rule_engine",
            "timestamp": datetime.utcnow().isoformat(),
            "decision": rule_result.decision.value,
            "confidence": rule_result.confidence,
            "rule_name": rule_result.rule_name,
        })
        
        return state
    
    def _node_urgency_agent(self, state: ProcessingState) -> ProcessingState:
        """Node: Call LLM agent only if rule engine returned UNDECIDED."""
        message = state["message"]
        
        # If rule engine was decisive, skip LLM
        if state["rule_decision"] != UrgencyDecision.UNDECIDED:
            state["urgency_agent_decision"] = state["rule_decision"]
            state["urgency_agent_confidence"] = state["rule_confidence"]
            state["urgency_agent_reasoning"] = "Skipped - rule engine was decisive"
            
            logger.debug(
                "Urgency agent skipped - rule engine decisive",
                rule_decision=state["rule_decision"].value
            )
            
            state["audit_trail"].append({
                "step": "urgency_agent",
                "timestamp": datetime.utcnow().isoformat(),
                "skipped": True,
                "reason": "rule_engine_decisive",
            })
            
            return state
        
        # Rule engine undecided - call LLM
        logger.debug("Calling urgency agent for UNDECIDED case")
        
        try:
            # Get urgency agent
            urgency_agent = get_urgency_agent()
            
            # Run agent (in sync context, use fallback)
            agent_decision, agent_confidence, agent_reasoning = \
                self._urgency_agent_sync(message)
            
            state["urgency_agent_decision"] = agent_decision
            state["urgency_agent_confidence"] = agent_confidence
            state["urgency_agent_reasoning"] = agent_reasoning
            
            logger.info(
                "Urgency agent decision",
                decision=agent_decision.value,
                confidence=agent_confidence
            )
            
            state["audit_trail"].append({
                "step": "urgency_agent",
                "timestamp": datetime.utcnow().isoformat(),
                "decision": agent_decision.value,
                "confidence": agent_confidence,
                "reasoning": agent_reasoning[:100],  # Truncate for audit
                "llm_called": True,
            })
            
            return state
            
        except Exception as e:
            logger.error("Urgency agent error", error=str(e))
            # Fallback: be conservative and mark as not_urgent
            state["urgency_agent_decision"] = UrgencyDecision.NOT_URGENT
            state["urgency_agent_confidence"] = 0.5
            state["urgency_agent_reasoning"] = f"Agent error - conservative fallback: {str(e)}"
            return state
    
    @staticmethod
    def _urgency_agent_sync(message) -> tuple[UrgencyDecision, float, str]:
        """Synchronous urgency agent (uses heuristics in sync context)."""
        text = message.content.text or message.content.caption or ""
        
        # Check for urgent keywords
        urgent_keywords = [
            "urgente", "urgent", "imediato", "immediate",
            "emergência", "emergency", "crítico", "critical",
            "ação requerida", "action required", "agora", "now",
            "confirmação", "confirmation", "validar", "verify",
            "código", "code", "token", "acesso", "access"
        ]
        
        text_lower = text.lower()
        urgent_count = sum(1 for kw in urgent_keywords if kw in text_lower)
        
        if urgent_count >= 3:
            return UrgencyDecision.URGENT, 0.85, "Multiple urgent keywords detected by agent"
        elif urgent_count >= 1:
            return UrgencyDecision.URGENT, 0.70, "Single urgent keyword detected by agent"
        else:
            return UrgencyDecision.NOT_URGENT, 0.65, "No urgent keywords detected by agent"
    
    def _node_classification_agent(self, state: ProcessingState) -> ProcessingState:
        """
        Node: Final classification with cognitive categories and summaries.
        
        Uses the enhanced ClassificationAgent to:
        - Assign cognitive-friendly categories
        - Generate short summaries for digest
        - Determine routing (immediate, digest, spam)
        - Maintain tenant isolation (no cross-user data)
        """
        message = state["message"]
        
        # Determine urgency decision (rule or agent)
        urgency_decision = state.get("urgency_agent_decision") or state["rule_decision"]
        urgency_confidence = state.get("urgency_agent_confidence") or state["rule_confidence"]
        
        logger.debug(
            "Running classification agent",
            tenant_id=message.tenant_id,
            user_id=message.user_id,
            urgency_decision=urgency_decision.value if urgency_decision else None
        )
        
        try:
            # Get classification agent
            classification_agent = get_classification_agent()
            
            # Run classification (sync wrapper for async method)
            result = self._classification_agent_sync(
                message,
                urgency_decision or UrgencyDecision.NOT_URGENT,
                urgency_confidence
            )
            
            # Update state with full classification result
            state["classification_result"] = result
            state["classification_category"] = result.category
            state["classification_summary"] = result.summary
            state["classification_routing"] = result.routing
            state["classification_reasoning"] = result.reasoning
            
            logger.info(
                "Classification agent result",
                tenant_id=message.tenant_id,
                user_id=message.user_id,
                category=result.category,
                routing=result.routing,
                summary_length=len(result.summary)
            )
            
            # Audit trail
            state["audit_trail"].append({
                "step": "classification_agent",
                "timestamp": datetime.utcnow().isoformat(),
                "category": result.category,
                "summary": result.summary,
                "routing": result.routing,
                "confidence": result.confidence,
                "reasoning": result.reasoning[:150],  # Truncate for audit
            })
            
            return state
            
        except Exception as e:
            logger.error(
                "Classification agent error",
                error=str(e),
                tenant_id=message.tenant_id
            )
            
            # Conservative fallback
            from jaiminho_notificacoes.processing.agents import ClassificationResult
            
            fallback_result = ClassificationResult(
                category="❓ Outros",
                summary="Erro no processamento - mensagem preservada",
                routing="digest" if urgency_decision != UrgencyDecision.URGENT else "immediate",
                reasoning=f"Fallback devido a erro: {str(e)}",
                confidence=0.5
            )
            
            state["classification_result"] = fallback_result
            state["classification_category"] = fallback_result.category
            state["classification_summary"] = fallback_result.summary
            state["classification_routing"] = fallback_result.routing
            state["classification_reasoning"] = fallback_result.reasoning
            
            return state
    
    @staticmethod
    def _classification_agent_sync(
        message: NormalizedMessage,
        urgency_decision: UrgencyDecision,
        urgency_confidence: float
    ) -> ClassificationResult:
        """
        Synchronous wrapper for classification agent.
        
        In production with async context, this would use await.
        For now, provides a simplified synchronous classification.
        """
        # Import here to avoid circular dependencies
        from jaiminho_notificacoes.processing.agents import ClassificationResult
        
        text = message.content.text or message.content.caption or ""
        text_lower = text.lower()
        
        # Simple category classification based on keywords
        category = "❓ Outros"
        
        if any(kw in text_lower for kw in ["trabalho", "reunião", "meeting", "projeto", "prazo", "deadline", "contrato"]):
            category = "💼 Trabalho e Negócios"
        elif any(kw in text_lower for kw in ["família", "mãe", "pai", "filho", "amigo", "querido"]):
            category = "👨‍👩‍👧 Família e Amigos"
        elif any(kw in text_lower for kw in ["entrega", "pedido", "compra", "rastreio", "correios", "sedex"]):
            category = "📦 Entregas e Compras"
        elif any(kw in text_lower for kw in ["pagamento", "boleto", "fatura", "pix", "transferência", "banco"]):
            category = "💰 Financeiro"
        elif any(kw in text_lower for kw in ["médico", "consulta", "exame", "saúde", "hospital", "remédio"]):
            category = "🏥 Saúde"
        elif any(kw in text_lower for kw in ["evento", "festa", "convite", "aniversário", "celebração"]):
            category = "🎉 Eventos e Convites"
        elif any(kw in text_lower for kw in ["bot", "automático", "notificação", "alerta", "sistema"]):
            category = "🤖 Automação e Bots"
        else:
            category = "📰 Informação Geral"
        
        # Generate simple summary
        sender_name = message.sender_name or "Contato"
        summary_prefix = f"{sender_name}: "
        
        # Truncate text for summary
        max_text_len = 100 - len(summary_prefix)
        summary_text = text[:max_text_len]
        if len(text) > max_text_len:
            summary_text += "..."
        
        summary = summary_prefix + summary_text
        
        # Determine routing based on urgency
        if urgency_decision == UrgencyDecision.URGENT and urgency_confidence > 0.75:
            routing = "immediate"
            reasoning = "Alta urgência detectada"
        elif urgency_decision == UrgencyDecision.NOT_URGENT:
            routing = "digest"
            reasoning = "Mensagem para digest diário"
        else:
            routing = "digest"
            reasoning = "Classificação padrão para digest"
        
        return ClassificationResult(
            category=category,
            summary=summary,
            routing=routing,
            reasoning=reasoning,
            confidence=0.7
        )
    
    def _node_route_decision(self, state: ProcessingState) -> ProcessingState:
        """Node: Make final routing decision based on classification."""
        routing = state["classification_routing"]
        
        state["final_decision"] = routing
        
        logger.info(
            "Final routing decision",
            routing=routing,
            category=state["classification_category"]
        )
        
        state["audit_trail"].append({
            "step": "route_decision",
            "timestamp": datetime.utcnow().isoformat(),
            "final_decision": routing,
            "category": state["classification_category"],
            "summary": state["classification_summary"],
        })
        
        return state
    
    def _node_audit_log(self, state: ProcessingState) -> ProcessingState:
        """Node: Log complete audit trail."""
        message = state["message"]
        
        audit_summary = {
            "message_id": message.message_id,
            "tenant_id": message.tenant_id,
            "user_id": message.user_id,
            "sender_phone": message.sender_phone,
            "final_decision": state["final_decision"],
            "rule_decision": state["rule_decision"].value if state["rule_decision"] else None,
            "urgency_agent_used": state["rule_decision"] == UrgencyDecision.UNDECIDED,
            "total_steps": len(state["audit_trail"]),
            "processing_time_ms": None,  # Would calculate real timing
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        logger.info(
            "Processing audit summary",
            audit=audit_summary
        )
        
        # Could persist to DynamoDB audit table here
        state["audit_trail"].append({
            "step": "audit_log",
            "timestamp": datetime.utcnow().isoformat(),
            "summary": audit_summary,
        })
        
        return state


# Global singleton
_orchestrator: Optional[MessageProcessingOrchestrator] = None


def get_orchestrator() -> MessageProcessingOrchestrator:
    """Get or create global orchestrator instance."""
    global _orchestrator
    
    if _orchestrator is None:
        _orchestrator = MessageProcessingOrchestrator()
    
    return _orchestrator

