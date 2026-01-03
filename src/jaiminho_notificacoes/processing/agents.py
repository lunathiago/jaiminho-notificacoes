"""LLM-based agents for message processing decisions."""

import json
import os
from typing import Tuple
from abc import ABC, abstractmethod

from jaiminho_notificacoes.processing.urgency_engine import UrgencyDecision
from jaiminho_notificacoes.core.logger import TenantContextLogger
from jaiminho_notificacoes.persistence.models import NormalizedMessage


logger = TenantContextLogger(__name__)


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
    
    Called when Rule Engine returns UNDECIDED.
    Uses structured prompting to classify messages as URGENT or NOT_URGENT.
    """
    
    async def run(
        self,
        message: NormalizedMessage,
        context: str = ""
    ) -> Tuple[UrgencyDecision, float, str]:
        """
        Classify message urgency using LLM.
        
        Args:
            message: The normalized message to classify
            context: Additional context (e.g., user history, patterns)
        
        Returns:
            (decision, confidence, reasoning)
        """
        logger.debug("Running urgency agent")
        
        try:
            # Extract text
            text = message.content.text or message.content.caption or ""
            
            # Build prompt
            prompt = self._build_urgency_prompt(message, text, context)
            
            # Call LLM (placeholder - would call OpenAI/Claude in production)
            response = await self._call_llm(prompt)
            
            # Parse response
            decision, confidence, reasoning = self._parse_urgency_response(response)
            
            logger.debug(
                "Urgency agent result",
                decision=decision.value,
                confidence=confidence
            )
            
            return decision, confidence, reasoning
            
        except Exception as e:
            logger.error(f"Urgency agent error: {e}")
            # Conservative fallback
            return UrgencyDecision.NOT_URGENT, 0.5, f"Agent error: {str(e)}"
    
    def _build_urgency_prompt(
        self,
        message: NormalizedMessage,
        text: str,
        context: str
    ) -> str:
        """Build prompt for urgency classification."""
        message_type = message.message_type.value if hasattr(message.message_type, 'value') else str(message.message_type)
        
        prompt = f"""You are an expert in analyzing message urgency for a Brazilian WhatsApp notification system.

Analyze the following message and determine its urgency level:

MESSAGE METADATA:
- Type: {message_type}
- From: {message.sender_name or message.sender_phone}
- Is Group: {message.metadata.is_group}
- Forwarded: {message.metadata.forwarded}

MESSAGE CONTENT (first 500 chars):
{text[:500]}

CONTEXT:
{context or "No additional context"}

CLASSIFICATION GUIDELINES:
- URGENT: Requires immediate action (financial alerts, security codes, emergencies, time-sensitive)
- NOT_URGENT: Can wait (general messages, marketing, casual conversation, information)

Respond with ONLY a valid JSON object (no markdown, no extra text):
{{
  "decision": "urgent" or "not_urgent",
  "confidence": <float 0.0-1.0>,
  "keywords_detected": [<list of key phrases>],
  "reasoning": "<brief explanation in Portuguese>"
}}"""
        
        return prompt
    
    async def _call_llm(self, prompt: str) -> str:
        """Call LLM API."""
        # Placeholder - in production would call OpenAI, Claude, etc.
        
        if not self.api_key:
            logger.warning("OPENAI_API_KEY not set - using fallback")
            return '{"decision": "not_urgent", "confidence": 0.5, "keywords_detected": [], "reasoning": "API não configurada"}'
        
        try:
            # Example: using langchain
            # from langchain.chat_models import ChatOpenAI
            # from langchain.schema import HumanMessage
            # 
            # chat = ChatOpenAI(model_name=self.model, temperature=0.2)
            # message = HumanMessage(content=prompt)
            # response = chat([message])
            # return response.content
            
            # For now, return mock response
            return '{"decision": "not_urgent", "confidence": 0.65, "keywords_detected": [], "reasoning": "Mensagem genérica"}'
            
        except Exception as e:
            logger.error(f"LLM API call failed: {e}")
            raise
    
    def _parse_urgency_response(
        self,
        response: str
    ) -> Tuple[UrgencyDecision, float, str]:
        """Parse LLM response."""
        try:
            data = json.loads(response)
            
            decision_str = data.get("decision", "not_urgent").lower()
            decision = (
                UrgencyDecision.URGENT 
                if decision_str == "urgent" 
                else UrgencyDecision.NOT_URGENT
            )
            
            confidence = float(data.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))  # Clamp to [0, 1]
            
            reasoning = data.get("reasoning", "No reasoning provided")
            
            return decision, confidence, reasoning
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response: {e}")
            raise


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
