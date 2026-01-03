"""SendPulse Feedback Handler for Jaiminho Notificações.

This module processes feedback button responses from SendPulse:
- Receives button clicks (Important / Not Important)
- Resolves user context internally via W-API instance mapping
- Updates interruption statistics via Learning Agent
- Influences future urgency decisions

Event structure from SendPulse webhook:
{
    "event": "message.reaction",
    "recipient": "+554899999999",
    "message_id": "sendpulse_msg_123",
    "button_reply": {
        "id": "important",
        "title": "Important"
    },
    "timestamp": 1705340400,
    "metadata": {
        "message_id": "jaiminho_notif_456",
        "wapi_instance_id": "instance-abc",
        "tenant_id": "tenant_1"
    }
}
"""

import json
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from jaiminho_notificacoes.core.logger import TenantContextLogger
from jaiminho_notificacoes.core.tenant import TenantIsolationMiddleware, TenantContext
from jaiminho_notificacoes.persistence.models import (
    FeedbackType,
    UserFeedbackRecord
)


logger = TenantContextLogger(__name__)


class SendPulseButtonType(str, Enum):
    """Button types from SendPulse."""
    IMPORTANT = "important"
    NOT_IMPORTANT = "not_important"


@dataclass
class SendPulseWebhookEvent:
    """SendPulse webhook event from button click."""
    event: str
    recipient: str  # User phone number
    message_id: str  # SendPulse message ID
    button_reply: Dict[str, str]  # {id, title}
    timestamp: int
    metadata: Dict[str, Any]  # Contains: message_id, wapi_instance_id, optional tenant_id


@dataclass
class FeedbackProcessingResult:
    """Result of feedback processing."""
    success: bool
    feedback_id: Optional[str] = None
    message_id: Optional[str] = None
    user_id: Optional[str] = None
    feedback_type: Optional[str] = None
    error: Optional[str] = None
    processing_time_ms: float = 0.0
    statistics_updated: bool = False


class SendPulseWebhookValidator:
    """Validates SendPulse webhook events."""

    @staticmethod
    def validate_event(event: Dict[str, Any]) -> tuple[bool, str]:
        """
        Validate webhook event structure.

        Args:
            event: Webhook event

        Returns:
            Tuple of (valid, error_message)
        """
        # Check required fields
        required_fields = ['event', 'recipient', 'message_id', 'button_reply', 'timestamp']
        for field in required_fields:
            if field not in event:
                return False, f"Missing required field: {field}"

        # Check metadata
        if 'metadata' not in event:
            return False, "Missing metadata (should contain: message_id, wapi_instance_id, optional tenant_id)"

        metadata = event['metadata']
        required_metadata = ['message_id', 'wapi_instance_id']
        for field in required_metadata:
            if field not in metadata:
                return False, f"Missing metadata field: {field}"

        if 'user_id' in metadata:
            return False, "metadata must not include user_id"

        # Check button reply structure
        button_reply = event['button_reply']
        if 'id' not in button_reply or 'title' not in button_reply:
            return False, "Invalid button_reply structure"

        # Check button ID
        try:
            button_type = SendPulseButtonType(button_reply['id'])
        except ValueError:
            return False, f"Unknown button type: {button_reply['id']}"

        # Check timestamp
        if not isinstance(event['timestamp'], int) or event['timestamp'] <= 0:
            return False, "Invalid timestamp"

        return True, ""

    @staticmethod
    def map_button_to_feedback(button_id: str) -> Optional[FeedbackType]:
        """
        Map SendPulse button ID to feedback type.

        Args:
            button_id: Button ID from SendPulse

        Returns:
            FeedbackType or None
        """
        mapping = {
            SendPulseButtonType.IMPORTANT.value: FeedbackType.IMPORTANT,
            SendPulseButtonType.NOT_IMPORTANT.value: FeedbackType.NOT_IMPORTANT,
        }
        return mapping.get(button_id)


class FeedbackMessageResolver:
    """Resolves original message information from metadata."""

    async def resolve_message_context(
        self,
        tenant_id: str,
        message_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve context about the original message.

        Args:
            tenant_id: Tenant ID
            message_id: Original Jaiminho message ID

        Returns:
            Message context or None if not found
        """
        # In a real implementation, this would query DynamoDB
        # For now, we'll return a placeholder
        # TODO: Implement DynamoDB query for message history
        logger.info(
            "Resolving message context",
            tenant_id=tenant_id,
            message_id=message_id
        )

        # This would typically query something like:
        # notifications_sent table
        # to get info about the original message

        return {
            'message_id': message_id,
            'sender_phone': '+1234567890',  # Would get from DB
            'sender_name': 'System',
            'category': 'system_alert',
            'sent_at': datetime.utcnow().isoformat()
        }


class UserFeedbackProcessor:
    """Processes user feedback and updates statistics."""

    def __init__(self):
        """Initialize processor."""
        self.validator = SendPulseWebhookValidator()
        self.resolver = FeedbackMessageResolver()
        self.middleware = TenantIsolationMiddleware()

    async def process_feedback(
        self,
        event: Dict[str, Any]
    ) -> FeedbackProcessingResult:
        """
        Process feedback from SendPulse button click.

        Args:
            event: Webhook event from SendPulse

        Returns:
            FeedbackProcessingResult
        """
        start_time = datetime.utcnow()

        try:
            # Validate event
            valid, error = self.validator.validate_event(event)
            if not valid:
                logger.warning(f"Invalid webhook event: {error}")
                return FeedbackProcessingResult(
                    success=False,
                    error=error
                )

            # Extract fields
            metadata = event['metadata']
            message_id = metadata['message_id']
            instance_id = metadata['wapi_instance_id']
            tenant_hint = metadata.get('tenant_id')
            button_id = event['button_reply']['id']
            timestamp = event['timestamp']

            # Resolve tenant context via W-API instance mapping
            tenant_payload = {'tenant_id': tenant_hint} if tenant_hint else None
            tenant_context, validation_errors = await self.middleware.validate_and_resolve(
                instance_id=instance_id,
                payload=tenant_payload
            )

            if not tenant_context:
                logger.security_validation_failed(
                    reason='Feedback webhook failed tenant resolution',
                    instance_id=instance_id,
                    tenant_id=tenant_hint,
                    details={'errors': validation_errors}
                )
                return FeedbackProcessingResult(
                    success=False,
                    error='Unauthorized: invalid or inactive W-API instance'
                )

            if tenant_hint and tenant_hint != tenant_context.tenant_id:
                logger.security_validation_failed(
                    reason='Feedback metadata tenant mismatch',
                    instance_id=instance_id,
                    tenant_id=tenant_context.tenant_id,
                    details={'metadata_tenant': tenant_hint}
                )
                return FeedbackProcessingResult(
                    success=False,
                    error='Unauthorized: tenant mismatch'
                )

            logger.set_context(
                tenant_id=tenant_context.tenant_id,
                user_id=tenant_context.user_id,
                instance_id=tenant_context.instance_id
            )

            # Map button to feedback type
            feedback_type = self.validator.map_button_to_feedback(button_id)
            if not feedback_type:
                return FeedbackProcessingResult(
                    success=False,
                    error=f"Unknown feedback type: {button_id}"
                )

            logger.info(
                "Processing feedback",
                tenant_id=tenant_context.tenant_id,
                user_id=tenant_context.user_id,
                message_id=message_id,
                feedback_type=feedback_type.value
            )

            # Resolve message context
            message_context = await self.resolver.resolve_message_context(
                tenant_context.tenant_id,
                message_id
            )

            if not message_context:
                logger.warning(
                    "Could not resolve message context",
                    tenant_id=tenant_context.tenant_id,
                    message_id=message_id
                )
                # Continue processing anyway (feedback is still valuable)
                message_context = {}

            # Create feedback record
            feedback_id = f"fb_{uuid.uuid4().hex[:12]}"

            feedback_record = UserFeedbackRecord(
                feedback_id=feedback_id,
                tenant_id=tenant_context.tenant_id,
                user_id=tenant_context.user_id,
                message_id=message_id,
                sender_phone=message_context.get('sender_phone', 'unknown'),
                sender_name=message_context.get('sender_name'),
                feedback_type=feedback_type.value,
                message_category=message_context.get('category'),
                was_interrupted=True,  # User saw and interacted with message
                user_response_time_seconds=self._calculate_response_time(
                    message_context.get('sent_at'),
                    timestamp
                ),
                feedback_timestamp=timestamp,
                feedback_reason=f"User clicked: {event['button_reply']['title']}"
            )

            logger.info(
                "Feedback record created",
                feedback_id=feedback_id,
                feedback_type=feedback_type.value
            )

            # Update Learning Agent statistics
            statistics_updated = await self._update_learning_agent(
                tenant_context,
                feedback_record
            )

            # Calculate processing time
            elapsed_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            result = FeedbackProcessingResult(
                success=True,
                feedback_id=feedback_id,
                message_id=message_id,
                user_id=tenant_context.user_id,
                feedback_type=feedback_type.value,
                processing_time_ms=elapsed_ms,
                statistics_updated=statistics_updated
            )

            logger.info(
                "Feedback processed successfully",
                feedback_id=feedback_id,
                processing_time_ms=elapsed_ms
            )

            return result

        except Exception as e:
            logger.error(f"Error processing feedback: {e}")
            elapsed_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            return FeedbackProcessingResult(
                success=False,
                error=f"Exception: {str(e)}",
                processing_time_ms=elapsed_ms
            )
        finally:
            logger.clear_context()

    @staticmethod
    def _calculate_response_time(sent_at: Optional[str], response_at: int) -> Optional[float]:
        """Calculate time between message sent and response."""
        if not sent_at:
            return None

        try:
            sent_dt = datetime.fromisoformat(sent_at)
            sent_ts = int(sent_dt.timestamp())
            response_seconds = response_at - sent_ts
            return max(0.0, float(response_seconds))
        except Exception:
            return None

    async def _update_learning_agent(
        self,
        tenant_context: TenantContext,
        feedback_record: UserFeedbackRecord
    ) -> bool:
        """
        Update Learning Agent with feedback.

        Args:
            tenant_context: Verified tenant context
            feedback_record: Feedback record to process

        Returns:
            True if update successful
        """
        try:
            from jaiminho_notificacoes.processing.learning_agent import (
                LearningAgent,
                FeedbackType as AgentFeedbackType
            )

            agent = LearningAgent()
            agent_feedback_type = AgentFeedbackType(feedback_record.feedback_type)
            await agent.process_feedback(
                tenant_context=tenant_context,
                message_id=feedback_record.message_id,
                sender_phone=feedback_record.sender_phone,
                sender_name=feedback_record.sender_name,
                feedback_type=agent_feedback_type,
                was_interrupted=feedback_record.was_interrupted,
                message_category=feedback_record.message_category,
                user_response_time_seconds=feedback_record.user_response_time_seconds,
                feedback_reason=feedback_record.feedback_reason,
            )

            logger.info(
                "Learning Agent updated",
                feedback_id=feedback_record.feedback_id,
                feedback_type=feedback_record.feedback_type
            )

            return True

        except ImportError:
            logger.warning("Learning Agent not available")
            return False

        except Exception as e:
            logger.error(f"Failed to update Learning Agent: {e}")
            return False


class FeedbackHandler:
    """High-level feedback handler."""

    def __init__(self):
        """Initialize handler."""
        self.processor = UserFeedbackProcessor()
        self.middleware = TenantIsolationMiddleware()

    async def handle_webhook(
        self,
        event: Dict[str, Any]
    ) -> FeedbackProcessingResult:
        """
        Handle incoming webhook from SendPulse.

        Args:
            event: Webhook event

        Returns:
            FeedbackProcessingResult
        """
        return await self.processor.process_feedback(event)

    async def handle_batch_webhooks(
        self,
        events: list[Dict[str, Any]]
    ) -> list[FeedbackProcessingResult]:
        """
        Handle multiple webhook events.

        Args:
            events: List of webhook events

        Returns:
            List of FeedbackProcessingResults
        """
        results = []
        for event in events:
            result = await self.handle_webhook(event)
            results.append(result)
        return results


# Singleton instance
_feedback_handler = None


def get_feedback_handler() -> FeedbackHandler:
    """Get or create feedback handler singleton."""
    global _feedback_handler
    if _feedback_handler is None:
        _feedback_handler = FeedbackHandler()
    return _feedback_handler
