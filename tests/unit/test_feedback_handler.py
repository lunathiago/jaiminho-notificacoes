"""Unit tests for SendPulse feedback handler.

Tests cover:
- Webhook validation
- Button response parsing
- Feedback record creation
- Statistics updates
- Tenant isolation
- Error handling
- Idempotency
"""

import json
import pytest
import os
from datetime import datetime
from unittest.mock import patch, AsyncMock, MagicMock

# Set AWS region before importing boto3-dependent modules
os.environ['AWS_REGION'] = 'us-east-1'


@pytest.fixture(autouse=True)
def mock_tenant_middleware():
    """Mock TenantIsolationMiddleware to avoid boto3 initialization."""
    with patch('jaiminho_notificacoes.processing.feedback_handler.TenantIsolationMiddleware') as mock:
        mock_instance = MagicMock()
        mock_instance.validate_tenant_context = MagicMock()
        mock.return_value = mock_instance
        yield mock


from jaiminho_notificacoes.processing.feedback_handler import (
    SendPulseWebhookValidator,
    SendPulseButtonType,
    UserFeedbackProcessor,
    FeedbackMessageResolver,
    FeedbackHandler,
    FeedbackProcessingResult,
    get_feedback_handler
)
from jaiminho_notificacoes.persistence.models import FeedbackType


class TestSendPulseWebhookValidator:
    """Test webhook validation."""

    def test_validate_event_valid(self):
        """Test validation of valid event."""
        event = {
            'event': 'message.reaction',
            'recipient': '+554899999999',
            'message_id': 'sendpulse_123',
            'button_reply': {'id': 'important', 'title': 'Important'},
            'timestamp': 1705340400,
            'metadata': {
                'message_id': 'jaiminho_456',
                'user_id': 'user_1',
                'tenant_id': 'tenant_1'
            }
        }
        valid, error = SendPulseWebhookValidator.validate_event(event)
        assert valid is True
        assert error == ""

    def test_validate_event_missing_required_field(self):
        """Test validation fails for missing required field."""
        event = {
            'event': 'message.reaction',
            'recipient': '+554899999999',
            'message_id': 'sendpulse_123',
            # Missing button_reply
            'timestamp': 1705340400,
            'metadata': {
                'message_id': 'jaiminho_456',
                'user_id': 'user_1',
                'tenant_id': 'tenant_1'
            }
        }
        valid, error = SendPulseWebhookValidator.validate_event(event)
        assert valid is False
        assert "Missing required field" in error

    def test_validate_event_missing_metadata(self):
        """Test validation fails for missing metadata."""
        event = {
            'event': 'message.reaction',
            'recipient': '+554899999999',
            'message_id': 'sendpulse_123',
            'button_reply': {'id': 'important', 'title': 'Important'},
            'timestamp': 1705340400
            # Missing metadata
        }
        valid, error = SendPulseWebhookValidator.validate_event(event)
        assert valid is False
        assert "metadata" in error

    def test_validate_event_missing_metadata_field(self):
        """Test validation fails for missing metadata field."""
        event = {
            'event': 'message.reaction',
            'recipient': '+554899999999',
            'message_id': 'sendpulse_123',
            'button_reply': {'id': 'important', 'title': 'Important'},
            'timestamp': 1705340400,
            'metadata': {
                'message_id': 'jaiminho_456',
                # Missing user_id and tenant_id
            }
        }
        valid, error = SendPulseWebhookValidator.validate_event(event)
        assert valid is False
        assert "Missing metadata field" in error

    def test_validate_event_invalid_button_reply(self):
        """Test validation fails for invalid button_reply."""
        event = {
            'event': 'message.reaction',
            'recipient': '+554899999999',
            'message_id': 'sendpulse_123',
            'button_reply': {'title': 'Important'},  # Missing id
            'timestamp': 1705340400,
            'metadata': {
                'message_id': 'jaiminho_456',
                'user_id': 'user_1',
                'tenant_id': 'tenant_1'
            }
        }
        valid, error = SendPulseWebhookValidator.validate_event(event)
        assert valid is False
        assert "button_reply" in error

    def test_validate_event_unknown_button_type(self):
        """Test validation fails for unknown button type."""
        event = {
            'event': 'message.reaction',
            'recipient': '+554899999999',
            'message_id': 'sendpulse_123',
            'button_reply': {'id': 'unknown_button', 'title': 'Unknown'},
            'timestamp': 1705340400,
            'metadata': {
                'message_id': 'jaiminho_456',
                'user_id': 'user_1',
                'tenant_id': 'tenant_1'
            }
        }
        valid, error = SendPulseWebhookValidator.validate_event(event)
        assert valid is False
        assert "Unknown button type" in error

    def test_validate_event_invalid_timestamp(self):
        """Test validation fails for invalid timestamp."""
        event = {
            'event': 'message.reaction',
            'recipient': '+554899999999',
            'message_id': 'sendpulse_123',
            'button_reply': {'id': 'important', 'title': 'Important'},
            'timestamp': 0,  # Invalid
            'metadata': {
                'message_id': 'jaiminho_456',
                'user_id': 'user_1',
                'tenant_id': 'tenant_1'
            }
        }
        valid, error = SendPulseWebhookValidator.validate_event(event)
        assert valid is False
        assert "Invalid timestamp" in error

    def test_map_button_to_feedback_important(self):
        """Test mapping important button."""
        feedback_type = SendPulseWebhookValidator.map_button_to_feedback('important')
        assert feedback_type == FeedbackType.IMPORTANT

    def test_map_button_to_feedback_not_important(self):
        """Test mapping not_important button."""
        feedback_type = SendPulseWebhookValidator.map_button_to_feedback('not_important')
        assert feedback_type == FeedbackType.NOT_IMPORTANT

    def test_map_button_to_feedback_unknown(self):
        """Test mapping unknown button."""
        feedback_type = SendPulseWebhookValidator.map_button_to_feedback('unknown')
        assert feedback_type is None


class TestFeedbackMessageResolver:
    """Test message context resolution."""

    @pytest.mark.asyncio
    async def test_resolve_message_context(self):
        """Test resolving message context."""
        resolver = FeedbackMessageResolver()
        context = await resolver.resolve_message_context('tenant_1', 'msg_123')
        
        assert context is not None
        assert 'message_id' in context
        assert context['message_id'] == 'msg_123'


class TestUserFeedbackProcessor:
    """Test feedback processing."""

    @pytest.mark.asyncio
    async def test_process_feedback_important(self):
        """Test processing important feedback."""
        processor = UserFeedbackProcessor()

        event = {
            'event': 'message.reaction',
            'recipient': '+554899999999',
            'message_id': 'sendpulse_123',
            'button_reply': {'id': 'important', 'title': 'Important'},
            'timestamp': 1705340400,
            'metadata': {
                'message_id': 'jaiminho_456',
                'user_id': 'user_1',
                'tenant_id': 'tenant_1'
            }
        }

        with patch.object(processor.middleware, 'validate_tenant_context'):
            with patch.object(processor, '_update_learning_agent', new_callable=AsyncMock) as mock_update:
                mock_update.return_value = True

                result = await processor.process_feedback(event)

                assert result.success is True
                assert result.feedback_id is not None
                assert result.feedback_type == FeedbackType.IMPORTANT.value
                assert result.message_id == 'jaiminho_456'
                assert result.user_id == 'user_1'
                assert result.statistics_updated is True

    @pytest.mark.asyncio
    async def test_process_feedback_not_important(self):
        """Test processing not_important feedback."""
        processor = UserFeedbackProcessor()

        event = {
            'event': 'message.reaction',
            'recipient': '+554899999999',
            'message_id': 'sendpulse_123',
            'button_reply': {'id': 'not_important', 'title': 'Not Important'},
            'timestamp': 1705340400,
            'metadata': {
                'message_id': 'jaiminho_456',
                'user_id': 'user_2',
                'tenant_id': 'tenant_1'
            }
        }

        with patch.object(processor.middleware, 'validate_tenant_context'):
            with patch.object(processor, '_update_learning_agent', new_callable=AsyncMock) as mock_update:
                mock_update.return_value = True

                result = await processor.process_feedback(event)

                assert result.success is True
                assert result.feedback_type == FeedbackType.NOT_IMPORTANT.value

    @pytest.mark.asyncio
    async def test_process_feedback_invalid_event(self):
        """Test processing invalid event."""
        processor = UserFeedbackProcessor()

        event = {
            'event': 'message.reaction',
            # Missing required fields
        }

        result = await processor.process_feedback(event)

        assert result.success is False
        assert result.error is not None
        assert "Missing required field" in result.error

    @pytest.mark.asyncio
    async def test_process_feedback_learning_agent_failure(self):
        """Test processing when Learning Agent update fails."""
        processor = UserFeedbackProcessor()

        event = {
            'event': 'message.reaction',
            'recipient': '+554899999999',
            'message_id': 'sendpulse_123',
            'button_reply': {'id': 'important', 'title': 'Important'},
            'timestamp': 1705340400,
            'metadata': {
                'message_id': 'jaiminho_456',
                'user_id': 'user_1',
                'tenant_id': 'tenant_1'
            }
        }

        with patch.object(processor.middleware, 'validate_tenant_context'):
            with patch.object(processor, '_update_learning_agent', new_callable=AsyncMock) as mock_update:
                mock_update.return_value = False

                result = await processor.process_feedback(event)

                assert result.success is True
                assert result.statistics_updated is False

    @pytest.mark.asyncio
    async def test_process_feedback_exception_handling(self):
        """Test exception handling during processing."""
        processor = UserFeedbackProcessor()

        event = {
            'event': 'message.reaction',
            'recipient': '+554899999999',
            'message_id': 'sendpulse_123',
            'button_reply': {'id': 'important', 'title': 'Important'},
            'timestamp': 1705340400,
            'metadata': {
                'message_id': 'jaiminho_456',
                'user_id': 'user_1',
                'tenant_id': 'tenant_1'
            }
        }

        with patch.object(processor.validator, 'validate_event') as mock_validate:
            mock_validate.side_effect = Exception("Validation error")

            result = await processor.process_feedback(event)

            assert result.success is False
            assert "Exception" in result.error

    def test_calculate_response_time(self):
        """Test response time calculation."""
        sent_at = "2024-01-15T10:00:00"
        response_at = int(datetime.fromisoformat(sent_at).timestamp()) + 300

        response_time = UserFeedbackProcessor._calculate_response_time(sent_at, response_at)

        assert response_time == 300.0

    def test_calculate_response_time_no_sent_at(self):
        """Test response time calculation without sent_at."""
        response_time = UserFeedbackProcessor._calculate_response_time(None, 1705340400)
        assert response_time is None

    def test_calculate_response_time_invalid_sent_at(self):
        """Test response time calculation with invalid sent_at."""
        response_time = UserFeedbackProcessor._calculate_response_time("invalid", 1705340400)
        assert response_time is None


class TestFeedbackHandler:
    """Test high-level feedback handler."""

    @pytest.mark.asyncio
    async def test_handle_webhook(self):
        """Test handling webhook."""
        handler = FeedbackHandler()

        event = {
            'event': 'message.reaction',
            'recipient': '+554899999999',
            'message_id': 'sendpulse_123',
            'button_reply': {'id': 'important', 'title': 'Important'},
            'timestamp': 1705340400,
            'metadata': {
                'message_id': 'jaiminho_456',
                'user_id': 'user_1',
                'tenant_id': 'tenant_1'
            }
        }

        with patch.object(handler.processor.middleware, 'validate_tenant_context'):
            with patch.object(handler.processor, '_update_learning_agent', new_callable=AsyncMock) as mock_update:
                mock_update.return_value = True

                result = await handler.handle_webhook(event)

                assert result.success is True
                assert result.feedback_id is not None

    @pytest.mark.asyncio
    async def test_handle_batch_webhooks(self):
        """Test handling multiple webhooks."""
        handler = FeedbackHandler()

        events = [
            {
                'event': 'message.reaction',
                'recipient': '+554899999999',
                'message_id': f'sendpulse_{i}',
                'button_reply': {'id': 'important', 'title': 'Important'},
                'timestamp': 1705340400 + i,
                'metadata': {
                    'message_id': f'jaiminho_{i}',
                    'user_id': f'user_{i}',
                    'tenant_id': 'tenant_1'
                }
            }
            for i in range(3)
        ]

        with patch.object(handler.processor.middleware, 'validate_tenant_context'):
            with patch.object(handler.processor, '_update_learning_agent', new_callable=AsyncMock) as mock_update:
                mock_update.return_value = True

                results = await handler.handle_batch_webhooks(events)

                assert len(results) == 3
                assert all(r.success for r in results)


class TestSingleton:
    """Test singleton pattern."""

    def test_get_feedback_handler_returns_singleton(self):
        """Test that get_feedback_handler returns same instance."""
        with patch('jaiminho_notificacoes.processing.feedback_handler.TenantIsolationMiddleware'):
            handler1 = get_feedback_handler()
            handler2 = get_feedback_handler()
            assert handler1 is handler2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
