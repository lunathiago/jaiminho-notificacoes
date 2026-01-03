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
    get_classification_agent
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
    
    classification_agent_decision: Literal["immediate", "digest", "spam"]
    classification_agent_reasoning: str
    
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
                "classification_agent_decision": "digest",
                "classification_agent_reasoning": "",
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
        """Node: Final classification for routing."""
        message = state["message"]
        
        # Determine urgency decision (rule or agent)
        urgency_decision = state.get("urgency_agent_decision") or state["rule_decision"]
        urgency_confidence = state.get("urgency_agent_confidence") or state["rule_confidence"]
        
        # Simple classification logic
        if urgency_decision == UrgencyDecision.URGENT:
            classification = "immediate"
            reasoning = "High urgency - send immediately"
        elif urgency_decision == UrgencyDecision.NOT_URGENT:
            classification = "digest"
            reasoning = "Low urgency - add to daily digest"
        else:
            # Fallback for any undecided cases
            classification = "digest"
            reasoning = "Unable to classify - adding to digest for later review"
        
        state["classification_agent_decision"] = classification
        state["classification_agent_reasoning"] = reasoning
        
        logger.debug(
            "Classification decision",
            urgency=urgency_decision.value,
            classification=classification,
            confidence=urgency_confidence
        )
        
        state["audit_trail"].append({
            "step": "classification_agent",
            "timestamp": datetime.utcnow().isoformat(),
            "classification": classification,
            "urgency_input": urgency_decision.value,
            "confidence": urgency_confidence,
        })
        
        return state
    
    def _node_route_decision(self, state: ProcessingState) -> ProcessingState:
        """Node: Make final routing decision."""
        classification = state["classification_agent_decision"]
        
        state["final_decision"] = classification
        
        logger.info(
            "Final routing decision",
            classification=classification
        )
        
        state["audit_trail"].append({
            "step": "route_decision",
            "timestamp": datetime.utcnow().isoformat(),
            "final_decision": classification,
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

