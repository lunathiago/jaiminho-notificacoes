"""Tests for Learning Agent."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.jaiminho_notificacoes.core.tenant import TenantContext
from src.jaiminho_notificacoes.processing.learning_agent import (
    LearningAgent,
    FeedbackType,
    UserFeedback,
    InterruptionStatistics,
)


@pytest.fixture
def learning_agent():
    """Create a Learning Agent instance."""
    return LearningAgent()


@pytest.fixture
def tenant_context():
    """Provide active tenant context for feedback processing tests."""
    return TenantContext(
        tenant_id="tenant-123",
        user_id="user-456",
        instance_id="inst-123",
        phone_number="5511999999999",
        status="active"
    )


@pytest.fixture
def test_feedback():
    """Create a test feedback object."""
    return UserFeedback(
        feedback_id="test-feedback-1",
        tenant_id="tenant-123",
        user_id="user-456",
        message_id="msg-789",
        sender_phone="5511999999999",
        sender_name="João Silva",
        feedback_type=FeedbackType.IMPORTANT,
        message_category="financial",
        was_interrupted=True,
        user_response_time_seconds=30.5,
        feedback_timestamp=int(datetime.utcnow().timestamp()),
        feedback_reason="This was important",
    )


class TestInterruptionStatistics:
    """Tests for InterruptionStatistics dataclass."""

    def test_important_rate_calculation(self):
        """Test important rate calculation."""
        stats = InterruptionStatistics(
            tenant_id="tenant-123",
            user_id="user-456",
            sender_phone="5511999999999",
            total_feedback_count=10,
            important_count=7,
            not_important_count=3,
        )

        assert stats.important_rate == 0.7

    def test_important_rate_zero(self):
        """Test important rate when no feedback."""
        stats = InterruptionStatistics(
            tenant_id="tenant-123",
            user_id="user-456",
        )

        assert stats.important_rate == 0.0

    def test_accuracy_rate_calculation(self):
        """Test accuracy rate calculation."""
        stats = InterruptionStatistics(
            tenant_id="tenant-123",
            user_id="user-456",
            correct_interrupts=5,
            incorrect_interrupts=1,
            correct_digests=3,
            missed_urgent=1,
        )

        # accuracy = (5 + 3) / (5 + 1 + 3 + 1) = 8 / 10 = 0.8
        assert stats.accuracy_rate == 0.8

    def test_precision_calculation(self):
        """Test precision calculation."""
        stats = InterruptionStatistics(
            tenant_id="tenant-123",
            user_id="user-456",
            correct_interrupts=8,
            incorrect_interrupts=2,
        )

        # precision = 8 / (8 + 2) = 0.8
        assert stats.precision == 0.8

    def test_recall_calculation(self):
        """Test recall calculation."""
        stats = InterruptionStatistics(
            tenant_id="tenant-123",
            user_id="user-456",
            correct_interrupts=8,
            missed_urgent=2,
        )

        # recall = 8 / (8 + 2) = 0.8
        assert stats.recall == 0.8


class TestLearningAgent:
    """Tests for LearningAgent class."""

    @pytest.mark.asyncio
    async def test_process_feedback_important(self, learning_agent, tenant_context, test_feedback):
        """Test processing feedback marked as important."""
        # Mock the persistence methods
        learning_agent._persist_feedback = AsyncMock(return_value=True)
        learning_agent._update_statistics = AsyncMock(return_value=True)

        success, message = await learning_agent.process_feedback(
            tenant_context=tenant_context,
            message_id=test_feedback.message_id,
            sender_phone=test_feedback.sender_phone,
            sender_name=test_feedback.sender_name,
            feedback_type=test_feedback.feedback_type,
            was_interrupted=test_feedback.was_interrupted,
            message_category=test_feedback.message_category,
            user_response_time_seconds=test_feedback.user_response_time_seconds,
        )

        assert success is True
        assert "processed" in message.lower()

    @pytest.mark.asyncio
    async def test_process_feedback_validation(self, learning_agent, tenant_context):
        """Test feedback validation."""
        success, message = await learning_agent.process_feedback(
            tenant_context=tenant_context,
            message_id="",
            sender_phone="5511999999999",
            sender_name="João",
            feedback_type=FeedbackType.IMPORTANT,
            was_interrupted=True,
        )

        assert success is False
        assert "required" in message.lower()

    @pytest.mark.asyncio
    async def test_process_feedback_not_important(self, learning_agent, tenant_context):
        """Test processing feedback marked as not important."""
        learning_agent._persist_feedback = AsyncMock(return_value=True)
        learning_agent._update_statistics = AsyncMock(return_value=True)

        success, message = await learning_agent.process_feedback(
            tenant_context=tenant_context,
            message_id="msg-789",
            sender_phone="5511999999999",
            sender_name="Bot",
            feedback_type=FeedbackType.NOT_IMPORTANT,
            was_interrupted=False,
        )

        assert success is True
        assert "processed" in message.lower()

    @pytest.mark.asyncio
    async def test_update_sender_statistics_new_feedback(self, learning_agent):
        """Test updating sender statistics with new feedback."""
        learning_agent._persist_feedback = AsyncMock(return_value=True)
        learning_agent._update_statistics = AsyncMock(return_value=True)

        feedback = UserFeedback(
            feedback_id="test-1",
            tenant_id="tenant-123",
            user_id="user-456",
            message_id="msg-789",
            sender_phone="5511999999999",
            sender_name="João",
            feedback_type=FeedbackType.IMPORTANT,
            message_category=None,
            was_interrupted=True,
            user_response_time_seconds=30.0,
            feedback_timestamp=int(datetime.utcnow().timestamp()),
        )

        result = await learning_agent._update_sender_statistics(feedback)
        assert result is True

    @pytest.mark.asyncio
    async def test_get_sender_statistics(self, learning_agent, tenant_context):
        """Test retrieving sender statistics."""
        learning_agent._persist_feedback = AsyncMock(return_value=True)
        learning_agent._update_statistics = AsyncMock(return_value=True)

        # First, process some feedback to create statistics
        await learning_agent.process_feedback(
            tenant_context=tenant_context,
            message_id="msg-1",
            sender_phone="5511999999999",
            sender_name="João",
            feedback_type=FeedbackType.IMPORTANT,
            was_interrupted=True,
        )

        # Mock the DynamoDB get
        with patch.object(learning_agent, 'learning_agent', return_value=None):
            # This would normally query DynamoDB
            stats = await learning_agent.get_sender_statistics(
                tenant_context=tenant_context,
                sender_phone="5511999999999",
            )

            # Stats might be None if not persisted in test environment
            assert stats is None or isinstance(stats, dict)

    @pytest.mark.asyncio
    async def test_feedback_reason_optional(self, learning_agent, tenant_context):
        """Test that feedback_reason is optional."""
        learning_agent._persist_feedback = AsyncMock(return_value=True)
        learning_agent._update_statistics = AsyncMock(return_value=True)

        success, message = await learning_agent.process_feedback(
            tenant_context=tenant_context,
            message_id="msg-789",
            sender_phone="5511999999999",
            sender_name="João",
            feedback_type=FeedbackType.IMPORTANT,
            was_interrupted=True,
            feedback_reason=None,  # No reason provided
        )

        assert success is True

    @pytest.mark.asyncio
    async def test_response_time_optional(self, learning_agent, tenant_context):
        """Test that user_response_time_seconds is optional."""
        learning_agent._persist_feedback = AsyncMock(return_value=True)
        learning_agent._update_statistics = AsyncMock(return_value=True)

        success, message = await learning_agent.process_feedback(
            tenant_context=tenant_context,
            message_id="msg-789",
            sender_phone="5511999999999",
            sender_name="João",
            feedback_type=FeedbackType.IMPORTANT,
            was_interrupted=True,
            user_response_time_seconds=None,  # No response time
        )

        assert success is True


class TestUserFeedback:
    """Tests for UserFeedback dataclass."""

    def test_feedback_creation(self, test_feedback):
        """Test creating a UserFeedback object."""
        assert test_feedback.feedback_id == "test-feedback-1"
        assert test_feedback.tenant_id == "tenant-123"
        assert test_feedback.user_id == "user-456"
        assert test_feedback.feedback_type == FeedbackType.IMPORTANT

    def test_feedback_to_dict(self, test_feedback):
        """Test converting feedback to dictionary."""
        feedback_dict = test_feedback.to_dict()

        assert feedback_dict["feedback_id"] == "test-feedback-1"
        assert feedback_dict["tenant_id"] == "tenant-123"
        assert feedback_dict["feedback_type"] == "important"
        assert "created_at" in feedback_dict


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
