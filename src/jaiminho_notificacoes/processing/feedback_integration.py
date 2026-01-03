"""Feedback Handler Integration for Urgency Agent.

This module provides utilities to integrate feedback statistics
into urgency calculations and message processing decisions.

The Learning Agent maintains:
- User-level statistics (how important is feedback for this user?)
- Sender-level statistics (how reliable is this sender?)
- Category-level statistics (how urgent is this category?)

These statistics influence future urgency decisions:
- If a sender has high false-positive rate → lower urgency
- If a category has high accuracy → increase urgency
- If a user rarely marks as important → increase digest batching
"""

from dataclasses import dataclass
from typing import Optional

from jaiminho_notificacoes.persistence.models import InterruptionStatisticsRecord


@dataclass
class FeedbackStatistics:
    """Aggregated feedback statistics for decision making."""

    total_feedback_count: int
    important_count: int
    not_important_count: int
    importance_rate: float  # important_count / total_feedback_count
    false_positive_rate: float  # not_important_count / total_feedback_count
    accuracy_score: float  # 0.0 to 1.0 based on patterns


class StatisticsAggregator:
    """Aggregates statistics for urgency decisions."""

    @staticmethod
    def aggregate_from_record(
        record: InterruptionStatisticsRecord
    ) -> FeedbackStatistics:
        """
        Convert InterruptionStatisticsRecord to decision-making statistics.

        Args:
            record: Statistics record from DynamoDB

        Returns:
            FeedbackStatistics for use in urgency calculations
        """
        total_count = record.total_feedback_count
        if total_count == 0:
            importance_rate = 0.5  # Default to neutral
            false_positive_rate = 0.5
            accuracy_score = 0.5
        else:
            importance_rate = record.important_count / total_count
            false_positive_rate = record.not_important_count / total_count
            accuracy_score = importance_rate  # Higher importance rate = better

        return FeedbackStatistics(
            total_feedback_count=total_count,
            important_count=record.important_count,
            not_important_count=record.not_important_count,
            importance_rate=importance_rate,
            false_positive_rate=false_positive_rate,
            accuracy_score=accuracy_score,
        )


class UrgencyInfluencer:
    """Applies feedback statistics to urgency calculations."""

    # Constants for influence factors
    MIN_FEEDBACK_COUNT_FOR_INFLUENCE = 5
    MIN_ACCURACY_FOR_BOOST = 0.7
    MAX_ACCURACY_FOR_REDUCTION = 0.3

    @staticmethod
    def apply_sender_influence(
        base_urgency: float,
        sender_stats: Optional[FeedbackStatistics]
    ) -> float:
        """
        Apply sender reliability to urgency score.

        High accuracy → boost urgency
        Low accuracy (high false positives) → reduce urgency

        Args:
            base_urgency: Original urgency score (0.0 to 1.0)
            sender_stats: Sender's historical statistics

        Returns:
            Adjusted urgency score
        """
        if not sender_stats or sender_stats.total_feedback_count < 5:
            return base_urgency  # Not enough data

        # Boost for reliable senders
        if sender_stats.accuracy_score >= UrgencyInfluencer.MIN_ACCURACY_FOR_BOOST:
            boost = (sender_stats.accuracy_score - 0.5) * 0.3  # Up to +0.15
            return min(1.0, base_urgency + boost)

        # Reduce for unreliable senders
        if sender_stats.accuracy_score <= UrgencyInfluencer.MAX_ACCURACY_FOR_REDUCTION:
            reduction = (0.5 - sender_stats.accuracy_score) * 0.2  # Up to -0.1
            return max(0.0, base_urgency - reduction)

        return base_urgency

    @staticmethod
    def apply_category_influence(
        base_urgency: float,
        category_stats: Optional[FeedbackStatistics]
    ) -> float:
        """
        Apply category feedback patterns to urgency.

        Categories marked as important historically → boost
        Categories marked as not important → reduce

        Args:
            base_urgency: Original urgency score (0.0 to 1.0)
            category_stats: Category's historical statistics

        Returns:
            Adjusted urgency score
        """
        if not category_stats or category_stats.total_feedback_count < 10:
            return base_urgency  # Not enough data

        # Use importance_rate as a multiplier
        multiplier = 0.8 + (category_stats.importance_rate * 0.4)  # 0.8 to 1.2
        return min(1.0, base_urgency * multiplier)

    @staticmethod
    def apply_user_influence(
        base_urgency: float,
        user_stats: Optional[FeedbackStatistics]
    ) -> float:
        """
        Apply user preferences to urgency.

        Users who rarely mark as important prefer digests.
        Users who frequently mark as important prefer interrupts.

        Args:
            base_urgency: Original urgency score (0.0 to 1.0)
            user_stats: User's historical statistics

        Returns:
            Adjusted urgency score
        """
        if not user_stats or user_stats.total_feedback_count < 5:
            return base_urgency  # Not enough data

        # Users with low importance rate prefer batching
        if user_stats.importance_rate < 0.3:
            reduction = (0.3 - user_stats.importance_rate) * 0.15
            return max(0.0, base_urgency - reduction)

        # Users with high importance rate respond well to interrupts
        if user_stats.importance_rate > 0.7:
            boost = (user_stats.importance_rate - 0.7) * 0.1
            return min(1.0, base_urgency + boost)

        return base_urgency

    @staticmethod
    def apply_all_influences(
        base_urgency: float,
        sender_stats: Optional[FeedbackStatistics] = None,
        category_stats: Optional[FeedbackStatistics] = None,
        user_stats: Optional[FeedbackStatistics] = None,
    ) -> tuple[float, dict]:
        """
        Apply all available influences to urgency.

        Applies influences in order:
        1. Sender reliability
        2. Category patterns
        3. User preferences

        Args:
            base_urgency: Original urgency score (0.0 to 1.0)
            sender_stats: Sender's statistics (optional)
            category_stats: Category's statistics (optional)
            user_stats: User's statistics (optional)

        Returns:
            Tuple of (adjusted_urgency, influences_applied)
            influences_applied is a dict with the influence details
        """
        urgency = base_urgency
        influences = {
            'original': base_urgency,
            'sender_applied': False,
            'category_applied': False,
            'user_applied': False,
        }

        # Apply sender influence
        if sender_stats:
            prev = urgency
            urgency = UrgencyInfluencer.apply_sender_influence(urgency, sender_stats)
            if urgency != prev:
                influences['sender_applied'] = True
                influences['sender_change'] = urgency - prev

        # Apply category influence
        if category_stats:
            prev = urgency
            urgency = UrgencyInfluencer.apply_category_influence(urgency, category_stats)
            if urgency != prev:
                influences['category_applied'] = True
                influences['category_change'] = urgency - prev

        # Apply user influence
        if user_stats:
            prev = urgency
            urgency = UrgencyInfluencer.apply_user_influence(urgency, user_stats)
            if urgency != prev:
                influences['user_applied'] = True
                influences['user_change'] = urgency - prev

        influences['final'] = urgency
        return urgency, influences


class BatchingDecisionMaker:
    """Determines whether to batch messages based on feedback."""

    @staticmethod
    def should_batch_for_user(
        user_stats: Optional[FeedbackStatistics]
    ) -> bool:
        """
        Determine if messages should be batched for a user.

        Users who consistently mark as "not important" benefit from digest batching.

        Args:
            user_stats: User's feedback statistics

        Returns:
            True if messages should be batched
        """
        if not user_stats or user_stats.total_feedback_count < 10:
            return False  # Not enough data, use default

        # If more than 50% of feedback is "not important" → batch
        return user_stats.false_positive_rate > 0.5

    @staticmethod
    def get_batching_interval_hours(
        user_stats: Optional[FeedbackStatistics]
    ) -> int:
        """
        Get recommended batching interval for a user.

        Users with low importance rates → longer batching windows
        Users with high importance rates → shorter or no batching

        Args:
            user_stats: User's feedback statistics

        Returns:
            Interval in hours (0 = no batching, 24 = daily digest)
        """
        if not user_stats or user_stats.total_feedback_count < 10:
            return 4  # Default: 4-hour batches

        # Scale from 0 to 24 hours based on importance rate
        # Low importance → longer batching (24 hours)
        # High importance → no batching (0 hours)
        if user_stats.importance_rate > 0.7:
            return 0  # No batching

        if user_stats.importance_rate < 0.3:
            return 24  # Daily digest

        # In between
        interval = int(24 * (1.0 - user_stats.importance_rate))
        return max(0, min(24, interval))


# Example usage in Urgency Agent
def example_urgency_calculation_with_feedback():
    """
    Example of how Urgency Agent would use feedback influence.

    This would be integrated into the Urgency Agent's calculate_urgency method.
    """

    # Hypothetical stats from Learning Agent
    sender_stats = FeedbackStatistics(
        total_feedback_count=20,
        important_count=18,
        not_important_count=2,
        importance_rate=0.9,
        false_positive_rate=0.1,
        accuracy_score=0.9,
    )

    category_stats = FeedbackStatistics(
        total_feedback_count=15,
        important_count=12,
        not_important_count=3,
        importance_rate=0.8,
        false_positive_rate=0.2,
        accuracy_score=0.8,
    )

    user_stats = FeedbackStatistics(
        total_feedback_count=50,
        important_count=25,
        not_important_count=25,
        importance_rate=0.5,
        false_positive_rate=0.5,
        accuracy_score=0.5,
    )

    # Base urgency from rule engine
    base_urgency = 0.6

    # Apply all influences
    adjusted_urgency, influences = UrgencyInfluencer.apply_all_influences(
        base_urgency=base_urgency,
        sender_stats=sender_stats,
        category_stats=category_stats,
        user_stats=user_stats,
    )

    print("Urgency Calculation with Feedback Influence:")
    print(f"  Base urgency: {base_urgency:.2f}")
    print(f"  After sender influence: {influences.get('sender_change', 0):+.3f}")
    print(f"  After category influence: {influences.get('category_change', 0):+.3f}")
    print(f"  After user influence: {influences.get('user_change', 0):+.3f}")
    print(f"  Final urgency: {adjusted_urgency:.2f}")

    # Batching decision
    should_batch = BatchingDecisionMaker.should_batch_for_user(user_stats)
    batch_hours = BatchingDecisionMaker.get_batching_interval_hours(user_stats)

    print(f"\nBatching Decision:")
    print(f"  Should batch: {should_batch}")
    print(f"  Interval: {batch_hours} hours")
