"""Learning Agent for feedback processing and interruption statistics.

This agent:
1. Processes binary feedback (important / not important)
2. Updates interruption statistics per user, sender, and category
3. Does NOT perform machine learning or model fine-tuning
4. Maintains audit trail of all feedback

Purpose:
- Track user feedback on message urgency decisions
- Build aggregated statistics for context in future decisions
- Enable feedback-driven improvements without ML
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
import boto3

from jaiminho_notificacoes.core.logger import TenantContextLogger
from jaiminho_notificacoes.core.tenant import TenantIsolationMiddleware
from jaiminho_notificacoes.persistence.models import (
    NormalizedMessage,
)


logger = TenantContextLogger(__name__)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')


class FeedbackType(str, Enum):
    """Binary feedback on message urgency."""
    IMPORTANT = "important"  # User found it important / should have been urgent
    NOT_IMPORTANT = "not_important"  # User found it not important / shouldn't have been urgent


@dataclass
class UserFeedback:
    """Single feedback entry from a user."""
    feedback_id: str
    tenant_id: str
    user_id: str
    message_id: str
    sender_phone: str
    sender_name: Optional[str]
    feedback_type: FeedbackType
    message_category: Optional[str]  # e.g., "financial", "marketing", "security"
    was_interrupted: bool  # Whether system marked as urgent
    user_response_time_seconds: Optional[float]  # How quickly user acted after notification
    feedback_timestamp: int
    feedback_reason: Optional[str] = None  # Optional user-provided reason
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return asdict(self)


@dataclass
class InterruptionStatistics:
    """Aggregated interruption statistics for a sender/category."""
    tenant_id: str
    user_id: str
    sender_phone: Optional[str] = None  # None means category-level stats
    category: Optional[str] = None  # Financial, Marketing, Security, etc.

    # Feedback counters
    total_feedback_count: int = 0
    important_count: int = 0
    not_important_count: int = 0

    # System accuracy metrics
    correct_interrupts: int = 0  # Marked urgent, user confirmed important
    incorrect_interrupts: int = 0  # Marked urgent, user said not important
    correct_digests: int = 0  # Marked digest, user confirmed not important
    missed_urgent: int = 0  # Missed marking as urgent, user said important

    # Response time statistics
    avg_response_time_seconds: float = 0.0
    total_response_time_seconds: float = 0.0
    response_count: int = 0

    # Time window
    window_start_timestamp: int = 0
    window_end_timestamp: int = 0
    last_updated: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @property
    def important_rate(self) -> float:
        """Percentage of feedbacks marked as important."""
        if self.total_feedback_count == 0:
            return 0.0
        return self.important_count / self.total_feedback_count

    @property
    def accuracy_rate(self) -> float:
        """System accuracy: correct decisions / total decisions."""
        total_correct = self.correct_interrupts + self.correct_digests
        total_decisions = (
            self.correct_interrupts + self.incorrect_interrupts +
            self.correct_digests + self.missed_urgent
        )
        if total_decisions == 0:
            return 0.0
        return total_correct / total_decisions

    @property
    def precision(self) -> float:
        """Precision: correct interrupts / all interrupts attempted."""
        total_interrupts = self.correct_interrupts + self.incorrect_interrupts
        if total_interrupts == 0:
            return 0.0
        return self.correct_interrupts / total_interrupts

    @property
    def recall(self) -> float:
        """Recall: correct interrupts / all important messages."""
        total_important = self.correct_interrupts + self.missed_urgent
        if total_important == 0:
            return 0.0
        return self.correct_interrupts / total_important

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        data = asdict(self)
        data['important_rate'] = self.important_rate
        data['accuracy_rate'] = self.accuracy_rate
        data['precision'] = self.precision
        data['recall'] = self.recall
        return data


class LearningAgent:
    """
    Processes user feedback and maintains interruption statistics.

    Responsibilities:
    1. Accept binary feedback on message urgency
    2. Update statistics per sender, category, and user
    3. Persist feedback to DynamoDB
    4. Provide statistics for context in future decisions
    5. Maintain audit trail
    """

    def __init__(self):
        """Initialize Learning Agent."""
        self.middleware = TenantIsolationMiddleware()
        self.feedback_table_name = os.getenv(
            'DYNAMODB_FEEDBACK_TABLE',
            'jaiminho-feedback'
        )
        self.stats_table_name = os.getenv(
            'DYNAMODB_INTERRUPTION_STATS_TABLE',
            'jaiminho-interruption-stats'
        )

    async def process_feedback(
        self,
        tenant_id: str,
        user_id: str,
        message_id: str,
        sender_phone: str,
        sender_name: Optional[str],
        feedback_type: FeedbackType,
        was_interrupted: bool,
        message_category: Optional[str] = None,
        user_response_time_seconds: Optional[float] = None,
        feedback_reason: Optional[str] = None,
    ) -> tuple[bool, str]:
        """
        Process user feedback on a message.

        Args:
            tenant_id: Tenant ID
            user_id: User ID
            message_id: Message ID being given feedback on
            sender_phone: Sender's phone number
            sender_name: Sender's name (optional)
            feedback_type: IMPORTANT or NOT_IMPORTANT
            was_interrupted: Whether system marked as urgent
            message_category: Message category (optional)
            user_response_time_seconds: How quickly user acted
            feedback_reason: Optional user-provided reason

        Returns:
            (success: bool, message: str)
        """
        try:
            # Validate inputs
            if not tenant_id or not user_id:
                return False, "tenant_id and user_id are required"

            if not message_id or not sender_phone:
                return False, "message_id and sender_phone are required"

            if feedback_type not in [FeedbackType.IMPORTANT, FeedbackType.NOT_IMPORTANT]:
                return False, f"Invalid feedback_type: {feedback_type}"

            logger.info(
                "Processing user feedback",
                tenant_id=tenant_id,
                user_id=user_id,
                feedback_type=feedback_type,
                was_interrupted=was_interrupted
            )

            # Create feedback entry
            import uuid
            feedback_id = str(uuid.uuid4())
            feedback_timestamp = int(datetime.utcnow().timestamp())

            feedback = UserFeedback(
                feedback_id=feedback_id,
                tenant_id=tenant_id,
                user_id=user_id,
                message_id=message_id,
                sender_phone=sender_phone,
                sender_name=sender_name,
                feedback_type=feedback_type,
                message_category=message_category,
                was_interrupted=was_interrupted,
                user_response_time_seconds=user_response_time_seconds,
                feedback_timestamp=feedback_timestamp,
                feedback_reason=feedback_reason,
            )

            # Persist feedback
            success = await self._persist_feedback(feedback)
            if not success:
                return False, "Failed to persist feedback"

            # Update statistics
            success = await self._update_statistics(feedback)
            if not success:
                logger.warning(
                    "Failed to update statistics after feedback",
                    feedback_id=feedback_id
                )

            logger.info(
                "Feedback processed successfully",
                feedback_id=feedback_id,
                feedback_type=feedback_type
            )

            return True, f"Feedback {feedback_id} processed"

        except Exception as e:
            logger.error(f"Error processing feedback: {e}")
            return False, f"Error: {str(e)}"

    async def _persist_feedback(self, feedback: UserFeedback) -> bool:
        """Persist feedback entry to DynamoDB."""
        try:
            table = dynamodb.Table(self.feedback_table_name)

            # DynamoDB item with tenant isolation
            item = {
                'PK': f"FEEDBACK#{feedback.tenant_id}#{feedback.user_id}",
                'SK': f"MESSAGE#{feedback.feedback_timestamp}#{feedback.feedback_id}",
                'feedback_id': feedback.feedback_id,
                'tenant_id': feedback.tenant_id,
                'user_id': feedback.user_id,
                'message_id': feedback.message_id,
                'sender_phone': feedback.sender_phone,
                'sender_name': feedback.sender_name or '',
                'feedback_type': feedback.feedback_type.value,
                'message_category': feedback.message_category or '',
                'was_interrupted': feedback.was_interrupted,
                'user_response_time_seconds': feedback.user_response_time_seconds or 0,
                'feedback_timestamp': feedback.feedback_timestamp,
                'feedback_reason': feedback.feedback_reason or '',
                'created_at': feedback.created_at,
                'ttl': int(feedback.feedback_timestamp) + (90 * 24 * 3600),  # 90 days TTL
            }

            table.put_item(Item=item)
            logger.debug("Feedback persisted to DynamoDB", feedback_id=feedback.feedback_id)
            return True

        except Exception as e:
            logger.error(f"Error persisting feedback: {e}")
            return False

    async def _update_statistics(self, feedback: UserFeedback) -> bool:
        """
        Update interruption statistics based on feedback.

        Updates three levels:
        1. Per-sender statistics for the user
        2. Per-category statistics for the user
        3. Overall user statistics
        """
        try:
            # Update sender-level statistics
            await self._update_sender_statistics(feedback)

            # Update category-level statistics (if provided)
            if feedback.message_category:
                await self._update_category_statistics(feedback)

            # Update overall user statistics
            await self._update_user_statistics(feedback)

            return True

        except Exception as e:
            logger.error(f"Error updating statistics: {e}")
            return False

    async def _update_sender_statistics(self, feedback: UserFeedback) -> bool:
        """Update per-sender interruption statistics."""
        try:
            table = dynamodb.Table(self.stats_table_name)

            # Get existing stats
            pk = f"STATS#{feedback.tenant_id}#{feedback.user_id}"
            sk = f"SENDER#{feedback.sender_phone}"

            try:
                response = table.get_item(Key={'PK': pk, 'SK': sk})
                existing = response.get('Item', {})
            except Exception:
                existing = {}

            # Calculate updates
            total_feedback = existing.get('total_feedback_count', 0) + 1
            important = existing.get('important_count', 0)
            not_important = existing.get('not_important_count', 0)
            correct_interrupts = existing.get('correct_interrupts', 0)
            incorrect_interrupts = existing.get('incorrect_interrupts', 0)
            correct_digests = existing.get('correct_digests', 0)
            missed_urgent = existing.get('missed_urgent', 0)

            # Update based on feedback type
            if feedback.feedback_type == FeedbackType.IMPORTANT:
                important += 1
                if feedback.was_interrupted:
                    correct_interrupts += 1
                else:
                    missed_urgent += 1
            else:  # NOT_IMPORTANT
                not_important += 1
                if feedback.was_interrupted:
                    incorrect_interrupts += 1
                else:
                    correct_digests += 1

            # Calculate response time average
            total_response_time = existing.get('total_response_time_seconds', 0)
            response_count = existing.get('response_count', 0)

            if feedback.user_response_time_seconds is not None:
                total_response_time += feedback.user_response_time_seconds
                response_count += 1

            avg_response_time = (
                total_response_time / response_count
                if response_count > 0
                else 0
            )

            # Current window (30 days)
            now = int(datetime.utcnow().timestamp())
            window_start = now - (30 * 24 * 3600)

            # Persist updated statistics
            item = {
                'PK': pk,
                'SK': sk,
                'tenant_id': feedback.tenant_id,
                'user_id': feedback.user_id,
                'sender_phone': feedback.sender_phone,
                'category': None,
                'total_feedback_count': total_feedback,
                'important_count': important,
                'not_important_count': not_important,
                'correct_interrupts': correct_interrupts,
                'incorrect_interrupts': incorrect_interrupts,
                'correct_digests': correct_digests,
                'missed_urgent': missed_urgent,
                'avg_response_time_seconds': avg_response_time,
                'total_response_time_seconds': total_response_time,
                'response_count': response_count,
                'window_start_timestamp': window_start,
                'window_end_timestamp': now,
                'last_updated': datetime.utcnow().isoformat(),
                'ttl': now + (90 * 24 * 3600),  # 90 days TTL
            }

            table.put_item(Item=item)
            logger.debug(
                "Sender statistics updated",
                sender_phone=feedback.sender_phone,
                total_feedback=total_feedback
            )
            return True

        except Exception as e:
            logger.error(f"Error updating sender statistics: {e}")
            return False

    async def _update_category_statistics(self, feedback: UserFeedback) -> bool:
        """Update per-category interruption statistics."""
        try:
            table = dynamodb.Table(self.stats_table_name)

            if not feedback.message_category:
                return True

            pk = f"STATS#{feedback.tenant_id}#{feedback.user_id}"
            sk = f"CATEGORY#{feedback.message_category}"

            try:
                response = table.get_item(Key={'PK': pk, 'SK': sk})
                existing = response.get('Item', {})
            except Exception:
                existing = {}

            # Calculate updates (same logic as sender stats)
            total_feedback = existing.get('total_feedback_count', 0) + 1
            important = existing.get('important_count', 0)
            not_important = existing.get('not_important_count', 0)
            correct_interrupts = existing.get('correct_interrupts', 0)
            incorrect_interrupts = existing.get('incorrect_interrupts', 0)
            correct_digests = existing.get('correct_digests', 0)
            missed_urgent = existing.get('missed_urgent', 0)

            if feedback.feedback_type == FeedbackType.IMPORTANT:
                important += 1
                if feedback.was_interrupted:
                    correct_interrupts += 1
                else:
                    missed_urgent += 1
            else:
                not_important += 1
                if feedback.was_interrupted:
                    incorrect_interrupts += 1
                else:
                    correct_digests += 1

            total_response_time = existing.get('total_response_time_seconds', 0)
            response_count = existing.get('response_count', 0)

            if feedback.user_response_time_seconds is not None:
                total_response_time += feedback.user_response_time_seconds
                response_count += 1

            avg_response_time = (
                total_response_time / response_count
                if response_count > 0
                else 0
            )

            now = int(datetime.utcnow().timestamp())
            window_start = now - (30 * 24 * 3600)

            item = {
                'PK': pk,
                'SK': sk,
                'tenant_id': feedback.tenant_id,
                'user_id': feedback.user_id,
                'sender_phone': None,
                'category': feedback.message_category,
                'total_feedback_count': total_feedback,
                'important_count': important,
                'not_important_count': not_important,
                'correct_interrupts': correct_interrupts,
                'incorrect_interrupts': incorrect_interrupts,
                'correct_digests': correct_digests,
                'missed_urgent': missed_urgent,
                'avg_response_time_seconds': avg_response_time,
                'total_response_time_seconds': total_response_time,
                'response_count': response_count,
                'window_start_timestamp': window_start,
                'window_end_timestamp': now,
                'last_updated': datetime.utcnow().isoformat(),
                'ttl': now + (90 * 24 * 3600),
            }

            table.put_item(Item=item)
            logger.debug(
                "Category statistics updated",
                category=feedback.message_category,
                total_feedback=total_feedback
            )
            return True

        except Exception as e:
            logger.error(f"Error updating category statistics: {e}")
            return False

    async def _update_user_statistics(self, feedback: UserFeedback) -> bool:
        """Update overall user-level statistics."""
        try:
            table = dynamodb.Table(self.stats_table_name)

            pk = f"STATS#{feedback.tenant_id}#{feedback.user_id}"
            sk = "USER#OVERALL"

            try:
                response = table.get_item(Key={'PK': pk, 'SK': sk})
                existing = response.get('Item', {})
            except Exception:
                existing = {}

            # Calculate updates
            total_feedback = existing.get('total_feedback_count', 0) + 1
            important = existing.get('important_count', 0)
            not_important = existing.get('not_important_count', 0)

            if feedback.feedback_type == FeedbackType.IMPORTANT:
                important += 1
            else:
                not_important += 1

            now = int(datetime.utcnow().timestamp())
            window_start = now - (30 * 24 * 3600)

            item = {
                'PK': pk,
                'SK': sk,
                'tenant_id': feedback.tenant_id,
                'user_id': feedback.user_id,
                'sender_phone': None,
                'category': None,
                'total_feedback_count': total_feedback,
                'important_count': important,
                'not_important_count': not_important,
                'window_start_timestamp': window_start,
                'window_end_timestamp': now,
                'last_updated': datetime.utcnow().isoformat(),
                'ttl': now + (90 * 24 * 3600),
            }

            table.put_item(Item=item)
            logger.debug(
                "User statistics updated",
                user_id=feedback.user_id,
                total_feedback=total_feedback
            )
            return True

        except Exception as e:
            logger.error(f"Error updating user statistics: {e}")
            return False

    async def get_sender_statistics(
        self,
        tenant_id: str,
        user_id: str,
        sender_phone: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve statistics for a sender.

        Used by Urgency Agent for context.
        """
        try:
            table = dynamodb.Table(self.stats_table_name)

            pk = f"STATS#{tenant_id}#{user_id}"
            sk = f"SENDER#{sender_phone}"

            response = table.get_item(Key={'PK': pk, 'SK': sk})
            item = response.get('Item')

            if not item:
                logger.debug(
                    "No statistics found for sender",
                    sender_phone=sender_phone
                )
                return None

            return item

        except Exception as e:
            logger.error(f"Error retrieving sender statistics: {e}")
            return None

    async def get_category_statistics(
        self,
        tenant_id: str,
        user_id: str,
        category: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve statistics for a category.

        Used by Urgency Agent for context.
        """
        try:
            table = dynamodb.Table(self.stats_table_name)

            pk = f"STATS#{tenant_id}#{user_id}"
            sk = f"CATEGORY#{category}"

            response = table.get_item(Key={'PK': pk, 'SK': sk})
            item = response.get('Item')

            if not item:
                logger.debug(
                    "No statistics found for category",
                    category=category
                )
                return None

            return item

        except Exception as e:
            logger.error(f"Error retrieving category statistics: {e}")
            return None

    async def get_user_statistics(
        self,
        tenant_id: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Retrieve overall statistics for a user."""
        try:
            table = dynamodb.Table(self.stats_table_name)

            pk = f"STATS#{tenant_id}#{user_id}"
            sk = "USER#OVERALL"

            response = table.get_item(Key={'PK': pk, 'SK': sk})
            item = response.get('Item')

            if not item:
                logger.debug("No statistics found for user", user_id=user_id)
                return None

            return item

        except Exception as e:
            logger.error(f"Error retrieving user statistics: {e}")
            return None

    async def get_recent_feedback(
        self,
        tenant_id: str,
        user_id: str,
        limit: int = 10,
        sender_phone: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve recent feedback entries.

        Optionally filtered by sender phone.
        """
        try:
            table = dynamodb.Table(self.feedback_table_name)

            pk = f"FEEDBACK#{tenant_id}#{user_id}"

            response = table.query(
                KeyConditionExpression='PK = :pk',
                ExpressionAttributeValues={':pk': pk},
                ScanIndexForward=False,
                Limit=limit
            )

            items = response.get('Items', [])

            # Filter by sender if provided
            if sender_phone:
                items = [
                    item for item in items
                    if item.get('sender_phone') == sender_phone
                ]

            return items

        except Exception as e:
            logger.error(f"Error retrieving recent feedback: {e}")
            return []
