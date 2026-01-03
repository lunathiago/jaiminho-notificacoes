"""Integration tests for complete feedback flow.

This module tests the entire feedback pipeline:
1. SendPulse webhook received
2. Validation and parsing
3. Feedback processing
4. Statistics update
5. Urgency influence calculation
"""

import pytest
import json
import os
from datetime import datetime
from unittest.mock import patch, AsyncMock, MagicMock

# Set AWS region
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
    get_feedback_handler,
    UserFeedbackProcessor
)
from jaiminho_notificacoes.processing.feedback_integration import (
    StatisticsAggregator,
    UrgencyInfluencer,
    FeedbackStatistics,
    BatchingDecisionMaker
)
from jaiminho_notificacoes.persistence.models import InterruptionStatisticsRecord
from jaiminho_notificacoes.lambda_handlers.process_feedback_webhook import (
    lambda_handler as feedback_lambda_handler
)


@pytest.fixture
def sample_webhook_event():
    """Sample webhook event from SendPulse."""
    return {
        'event': 'message.reaction',
        'recipient': '+554899999999',
        'message_id': 'sendpulse_abc123',
        'button_reply': {
            'id': 'important',
            'title': '🔴 Important'
        },
        'timestamp': int(datetime.utcnow().timestamp()),
        'metadata': {
            'message_id': 'jaiminho_notif_456',
            'user_id': 'user_alice',
            'tenant_id': 'company_acme',
            'sender_phone': '+5548988776655',
            'category': 'financial'
        }
    }


@pytest.fixture
def sample_statistics_record():
    """Sample interruption statistics record."""
    return InterruptionStatisticsRecord(
        tenant_id='company_acme',
        user_id='user_alice',
        sender_phone='+5548988776655',
        category='financial',
        total_feedback_count=20,
        important_count=18,
        not_important_count=2,
        correct_interrupts=15,
        incorrect_interrupts=2,
        correct_digests=1,
        missed_urgent=2,
        avg_response_time_seconds=300.0
    )


class TestEndToEndFeedbackFlow:
    """Test complete feedback processing flow."""

    @pytest.mark.asyncio
    async def test_complete_feedback_flow(self, sample_webhook_event):
        """Test complete flow from webhook to statistics update."""
        # 1. Receive webhook
        handler = get_feedback_handler()

        # Mock dependencies
        with patch.object(handler.processor.middleware, 'validate_tenant_context'):
            with patch.object(handler.processor, '_update_learning_agent', new_callable=AsyncMock) as mock_update:
                mock_update.return_value = True

                # 2. Process webhook
                result = await handler.handle_webhook(sample_webhook_event)

                # 3. Verify processing
                assert result.success is True
                assert result.feedback_id is not None
                assert result.message_id == 'jaiminho_notif_456'
                assert result.user_id == 'user_alice'
                assert result.feedback_type == 'important'
                assert result.statistics_updated is True

                # 4. Verify Learning Agent was called
                mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_lambda_handler_integration(self, sample_webhook_event):
        """Test Lambda handler with webhook."""
        # Simulate API Gateway event
        api_gateway_event = {
            'body': json.dumps(sample_webhook_event),
            'httpMethod': 'POST',
            'headers': {
                'Content-Type': 'application/json'
            }
        }

        # Mock the feedback handler result
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.feedback_id = 'fb_abc123'
        mock_result.processing_time_ms = 50.0
        mock_result.statistics_updated = True

        # Mock get_feedback_handler and asyncio.run
        with patch('jaiminho_notificacoes.lambda_handlers.process_feedback_webhook.get_feedback_handler') as mock_get_handler:
            with patch('jaiminho_notificacoes.lambda_handlers.process_feedback_webhook.asyncio.run') as mock_asyncio_run:
                mock_handler = MagicMock()
                mock_handler.handle_webhook = AsyncMock(return_value=mock_result)
                mock_get_handler.return_value = mock_handler

                # Mock asyncio.run to just call the coroutine
                async def run_coro(coro):
                    return await coro
                mock_asyncio_run.side_effect = run_coro

                # Call Lambda handler
                response = feedback_lambda_handler(api_gateway_event, None)

                # Verify response
                assert response['statusCode'] == 200
                body = json.loads(response['body'])
                assert body['status'] == 'success'
                assert body['feedback_id'] == 'fb_abc123'


class TestStatisticsIntegration:
    """Test statistics aggregation and urgency influence."""

    def test_statistics_to_urgency_influence(self, sample_statistics_record):
        """Test converting statistics to urgency influence."""
        # 1. Aggregate statistics
        stats = StatisticsAggregator.aggregate_from_record(sample_statistics_record)

        # 2. Verify aggregation
        assert stats.total_feedback_count == 20
        assert stats.important_count == 18
        assert stats.not_important_count == 2
        assert stats.importance_rate == 0.9
        assert stats.false_positive_rate == 0.1

        # 3. Apply urgency influence
        base_urgency = 0.6
        adjusted_urgency, influences = UrgencyInfluencer.apply_all_influences(
            base_urgency=base_urgency,
            sender_stats=stats
        )

        # 4. Verify influence
        assert adjusted_urgency > base_urgency  # High accuracy sender → boost
        assert influences['sender_applied'] is True

    def test_batching_decision_from_feedback(self):
        """Test batching decision based on feedback."""
        # User who marks most as "not important" → should batch
        low_importance_stats = FeedbackStatistics(
            total_feedback_count=20,
            important_count=4,
            not_important_count=16,
            importance_rate=0.2,
            false_positive_rate=0.8,
            accuracy_score=0.2
        )

        should_batch = BatchingDecisionMaker.should_batch_for_user(low_importance_stats)
        batch_hours = BatchingDecisionMaker.get_batching_interval_hours(low_importance_stats)

        assert should_batch is True
        assert batch_hours == 24  # Daily digest

        # User who marks most as "important" → shouldn't batch
        high_importance_stats = FeedbackStatistics(
            total_feedback_count=20,
            important_count=18,
            not_important_count=2,
            importance_rate=0.9,
            false_positive_rate=0.1,
            accuracy_score=0.9
        )

        should_batch = BatchingDecisionMaker.should_batch_for_user(high_importance_stats)
        batch_hours = BatchingDecisionMaker.get_batching_interval_hours(high_importance_stats)

        assert should_batch is False
        assert batch_hours == 0  # No batching


class TestMultiTenantFeedback:
    """Test multi-tenant feedback processing."""

    @pytest.mark.asyncio
    async def test_tenant_isolation_in_feedback(self):
        """Test that feedback respects tenant boundaries."""
        handler = get_feedback_handler()

        # Events from different tenants
        tenant1_event = {
            'event': 'message.reaction',
            'recipient': '+554899999999',
            'message_id': 'sendpulse_tenant1',
            'button_reply': {'id': 'important', 'title': 'Important'},
            'timestamp': int(datetime.utcnow().timestamp()),
            'metadata': {
                'message_id': 'jaiminho_t1',
                'user_id': 'user_t1',
                'tenant_id': 'tenant_1'
            }
        }

        tenant2_event = {
            'event': 'message.reaction',
            'recipient': '+554888888888',
            'message_id': 'sendpulse_tenant2',
            'button_reply': {'id': 'not_important', 'title': 'Not Important'},
            'timestamp': int(datetime.utcnow().timestamp()),
            'metadata': {
                'message_id': 'jaiminho_t2',
                'user_id': 'user_t2',
                'tenant_id': 'tenant_2'
            }
        }

        with patch.object(handler.processor.middleware, 'validate_tenant_context') as mock_validate:
            with patch.object(handler.processor, '_update_learning_agent', new_callable=AsyncMock) as mock_update:
                mock_update.return_value = True

                # Process both
                result1 = await handler.handle_webhook(tenant1_event)
                result2 = await handler.handle_webhook(tenant2_event)

                # Both successful
                assert result1.success is True
                assert result2.success is True

                # Different feedback IDs
                assert result1.feedback_id != result2.feedback_id

                # Tenant validation was called for each
                assert mock_validate.call_count == 2


class TestErrorRecovery:
    """Test error handling and recovery."""

    @pytest.mark.asyncio
    async def test_feedback_with_learning_agent_failure(self, sample_webhook_event):
        """Test graceful degradation when Learning Agent fails."""
        handler = get_feedback_handler()

        with patch.object(handler.processor.middleware, 'validate_tenant_context'):
            with patch.object(handler.processor, '_update_learning_agent', new_callable=AsyncMock) as mock_update:
                # Simulate Learning Agent failure
                mock_update.return_value = False

                result = await handler.handle_webhook(sample_webhook_event)

                # Feedback processing still succeeds
                assert result.success is True
                assert result.feedback_id is not None
                # But statistics not updated
                assert result.statistics_updated is False

    @pytest.mark.asyncio
    async def test_invalid_webhook_handling(self):
        """Test handling of invalid webhook."""
        handler = get_feedback_handler()

        invalid_event = {
            'event': 'message.reaction',
            # Missing required fields
        }

        result = await handler.handle_webhook(invalid_event)

        assert result.success is False
        assert result.error is not None
        assert result.feedback_id is None


class TestPerformance:
    """Test performance characteristics."""

    @pytest.mark.asyncio
    async def test_batch_webhook_performance(self):
        """Test processing multiple webhooks efficiently."""
        handler = get_feedback_handler()

        # Create 10 webhook events
        events = []
        for i in range(10):
            event = {
                'event': 'message.reaction',
                'recipient': f'+55489999998{i:02d}',
                'message_id': f'sendpulse_{i}',
                'button_reply': {
                    'id': 'important' if i % 2 == 0 else 'not_important',
                    'title': 'Important' if i % 2 == 0 else 'Not Important'
                },
                'timestamp': int(datetime.utcnow().timestamp()) + i,
                'metadata': {
                    'message_id': f'jaiminho_{i}',
                    'user_id': f'user_{i}',
                    'tenant_id': 'company_test'
                }
            }
            events.append(event)

        with patch.object(handler.processor.middleware, 'validate_tenant_context'):
            with patch.object(handler.processor, '_update_learning_agent', new_callable=AsyncMock) as mock_update:
                mock_update.return_value = True

                # Process batch
                results = await handler.handle_batch_webhooks(events)

                # All successful
                assert len(results) == 10
                assert all(r.success for r in results)

                # All processed quickly (< 1000ms each)
                assert all(r.processing_time_ms < 1000 for r in results)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
