"""Unit tests for LangGraph orchestrator."""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from jaiminho_notificacoes.processing.orchestrator import (
    MessageProcessingOrchestrator,
    get_orchestrator,
    ProcessingState
)
from jaiminho_notificacoes.processing.urgency_engine import UrgencyDecision
from jaiminho_notificacoes.persistence.models import (
    NormalizedMessage,
    MessageType,
    MessageContent,
    MessageMetadata,
    MessageSecurity,
    MessageSource,
    ProcessingDecision
)


@pytest.fixture
def orchestrator():
    """Create orchestrator instance with mocked dependencies."""
    with patch('jaiminho_notificacoes.processing.orchestrator.TenantResolver'):
        return MessageProcessingOrchestrator()


@pytest.fixture
def base_message():
    """Create base message for testing."""
    return NormalizedMessage(
        message_id="test-msg-001",
        tenant_id="tenant-abc",
        user_id="user-xyz",
        sender_phone="5511999999999",
        sender_name="Test Sender",
        message_type=MessageType.TEXT,
        content=MessageContent(text=""),
        timestamp=int(datetime.now().timestamp()),
        source=MessageSource(
            platform="wapi",
            instance_id="test-instance"
        ),
        metadata=MessageMetadata(chat_type="individual", is_group=False, from_me=False),
        security=MessageSecurity(
            validated_at=datetime.now().isoformat(),
            validation_passed=True,
            instance_verified=True,
            tenant_resolved=True,
            phone_ownership_verified=True
        )
    )


class TestOrchestratorFlow:
    """Test orchestrator workflow."""
    
    def test_urgent_message_skips_agent(self, orchestrator, base_message):
        """Test that urgent messages skip LLM agent."""
        base_message.content.text = "PIX de R$ 1.000,00 recebido"
        
        initial_state: ProcessingState = {
            "message": base_message,
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
        
        # Rule engine node
        state1 = orchestrator._node_rule_engine(initial_state)
        assert state1["rule_decision"] == UrgencyDecision.URGENT
        assert state1["rule_confidence"] > 0.8
        
        # Urgency agent should skip
        state2 = orchestrator._node_urgency_agent(state1)
        assert state2["urgency_agent_decision"] == UrgencyDecision.URGENT
        assert state2["urgency_agent_reasoning"] == "Skipped - rule engine was decisive"
        
        # Classification should be immediate (updated to use new fields)
        state3 = orchestrator._node_classification_agent(state2)
        assert state3["classification_routing"] == "immediate"
        assert state3["classification_category"] is not None
        assert state3["classification_summary"] is not None
        
        # Route decision
        state4 = orchestrator._node_route_decision(state3)
        assert state4["final_decision"] == "immediate"
        
        # Audit trail has all steps
        assert len(state4["audit_trail"]) >= 4
        assert any(step["step"] == "rule_engine" for step in state4["audit_trail"])
        assert any(step["step"] == "urgency_agent" for step in state4["audit_trail"])
    
    def test_undecided_message_calls_agent(self, orchestrator, base_message):
        """Test that UNDECIDED messages call LLM agent."""
        base_message.content.text = "Oi, como você está?"
        
        initial_state: ProcessingState = {
            "message": base_message,
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
        
        # Rule engine node
        state1 = orchestrator._node_rule_engine(initial_state)
        assert state1["rule_decision"] == UrgencyDecision.UNDECIDED
        assert state1["rule_confidence"] == 0.0
        
        # Urgency agent should call LLM (or fallback)
        state2 = orchestrator._node_urgency_agent(state1)
        assert state2["urgency_agent_decision"] in [
            UrgencyDecision.URGENT,
            UrgencyDecision.NOT_URGENT
        ]
        
        # Check audit shows agent was called
        agent_audit = next(
            (step for step in state2["audit_trail"] if step["step"] == "urgency_agent"),
            None
        )
        # Agent was called (not skipped)
        assert agent_audit is not None
    
    def test_not_urgent_message_to_digest(self, orchestrator, base_message):
        """Test NOT_URGENT classification routes to digest."""
        base_message.content.text = "Promoção: 50% de desconto!"
        
        initial_state: ProcessingState = {
            "message": base_message,
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
        
        state1 = orchestrator._node_rule_engine(initial_state)
        assert state1["rule_decision"] == UrgencyDecision.NOT_URGENT
        
        state2 = orchestrator._node_urgency_agent(state1)
        state3 = orchestrator._node_classification_agent(state2)
        assert state3["classification_agent_decision"] == "digest"
        
        state4 = orchestrator._node_route_decision(state3)
        assert state4["final_decision"] == "digest"
    
    def test_group_message_not_urgent(self, orchestrator, base_message):
        """Test that group messages are always NOT_URGENT."""
        base_message.metadata.chat_type = "group"
        base_message.metadata.is_group = True
        base_message.content.text = "Importante! Reunião urgente!"
        
        initial_state: ProcessingState = {
            "message": base_message,
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
        
        state1 = orchestrator._node_rule_engine(initial_state)
        assert state1["rule_decision"] == UrgencyDecision.NOT_URGENT
        
        state4 = orchestrator._node_route_decision(
            orchestrator._node_classification_agent(
                orchestrator._node_urgency_agent(state1)
            )
        )
        assert state4["final_decision"] == "digest"


class TestAuditTrail:
    """Test audit trail tracking."""
    
    def test_complete_audit_trail(self, orchestrator, base_message):
        """Test that complete audit trail is maintained."""
        base_message.content.text = "Código de verificação: 123456"
        
        initial_state: ProcessingState = {
            "message": base_message,
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
        
        state = initial_state
        state = orchestrator._node_rule_engine(state)
        state = orchestrator._node_urgency_agent(state)
        state = orchestrator._node_classification_agent(state)
        state = orchestrator._node_route_decision(state)
        state = orchestrator._node_audit_log(state)
        
        # Check audit trail
        assert len(state["audit_trail"]) >= 5
        
        steps = [entry["step"] for entry in state["audit_trail"]]
        assert "rule_engine" in steps
        assert "urgency_agent" in steps
        assert "classification_agent" in steps
        assert "route_decision" in steps
        assert "audit_log" in steps
        
        # All have timestamps
        for entry in state["audit_trail"]:
            assert "timestamp" in entry
    
    def test_audit_trail_user_scoped(self, orchestrator, base_message):
        """Test that audit trail is scoped by user_id."""
        base_message.content.text = "Test message"
        
        initial_state: ProcessingState = {
            "message": base_message,
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
        
        state = initial_state
        state = orchestrator._node_rule_engine(state)
        state = orchestrator._node_urgency_agent(state)
        state = orchestrator._node_classification_agent(state)
        state = orchestrator._node_route_decision(state)
        state = orchestrator._node_audit_log(state)
        
        # Find audit log entry
        audit_log_entry = next(
            e for e in state["audit_trail"] if e["step"] == "audit_log"
        )
        
        summary = audit_log_entry.get("summary", {})
        assert summary["user_id"] == base_message.user_id
        assert summary["tenant_id"] == base_message.tenant_id
        assert summary["message_id"] == base_message.message_id


class TestSingleton:
    """Test singleton pattern."""
    
    def test_get_orchestrator_singleton(self):
        """Test that get_orchestrator returns same instance."""
        with patch('jaiminho_notificacoes.processing.orchestrator.TenantResolver'):
            from jaiminho_notificacoes.processing.orchestrator import _orchestrator as current_orchestrator
            import jaiminho_notificacoes.processing.orchestrator as orch_module
            
            # Reset global
            orch_module._orchestrator = None
            
            orch1 = get_orchestrator()
            orch2 = get_orchestrator()
            
            assert orch1 is orch2


class TestRealWorldScenarios:
    """Test real-world scenarios."""
    
    def test_bank_alert_flow(self, orchestrator, base_message):
        """Test complete flow for bank alert."""
        base_message.content.text = "Alerta: Compra no cartão final 1234, R$ 599,90"
        
        initial_state: ProcessingState = {
            "message": base_message,
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
        
        state = initial_state
        state = orchestrator._node_rule_engine(state)
        state = orchestrator._node_urgency_agent(state)
        state = orchestrator._node_classification_agent(state)
        state = orchestrator._node_route_decision(state)
        
        assert state["final_decision"] == "immediate"
        assert state["rule_decision"] == UrgencyDecision.URGENT
    
    def test_marketing_newsletter_flow(self, orchestrator, base_message):
        """Test complete flow for marketing newsletter."""
        base_message.content.text = "Newsletter: Confira as novidades desta semana com 40% desconto"
        
        initial_state: ProcessingState = {
            "message": base_message,
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
        
        state = initial_state
        state = orchestrator._node_rule_engine(state)
        state = orchestrator._node_urgency_agent(state)
        state = orchestrator._node_classification_agent(state)
        state = orchestrator._node_route_decision(state)
        
        assert state["final_decision"] == "digest"
        assert state["rule_decision"] == UrgencyDecision.NOT_URGENT
    
    def test_generic_message_undecided_then_digest(self, orchestrator, base_message):
        """Test flow for generic message that becomes digest after agent."""
        base_message.content.text = "Oi tudo bem? Como foi seu dia?"
        
        initial_state: ProcessingState = {
            "message": base_message,
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
        
        state = initial_state
        state = orchestrator._node_rule_engine(state)
        
        # Should be UNDECIDED
        assert state["rule_decision"] == UrgencyDecision.UNDECIDED
        
        state = orchestrator._node_urgency_agent(state)
        state = orchestrator._node_classification_agent(state)
        state = orchestrator._node_route_decision(state)
        
        # Eventually should be digest (safe default)
        assert state["final_decision"] == "digest"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
