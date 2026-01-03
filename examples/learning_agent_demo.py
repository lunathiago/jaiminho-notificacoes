"""Example: Learning Agent with feedback processing.

This example demonstrates how to:
1. Process user feedback on message urgency
2. Update interruption statistics
3. Retrieve statistics for context
"""

import asyncio
import json
from datetime import datetime

from src.jaiminho_notificacoes.processing.learning_agent import (
    LearningAgent,
    FeedbackType,
)
from src.jaiminho_notificacoes.processing.learning_integration import (
    HistoricalDataProvider,
)


async def main():
    """Run Learning Agent example."""
    print("=" * 80)
    print("Learning Agent - User Feedback Example")
    print("=" * 80)

    learning_agent = LearningAgent()
    data_provider = HistoricalDataProvider()

    # Example 1: Process user feedback
    print("\n1. Processing user feedback...")
    print("-" * 80)

    success, message = await learning_agent.process_feedback(
        tenant_id="tenant-001",
        user_id="user-001",
        message_id="msg-12345",
        sender_phone="5511987654321",
        sender_name="Maria Silva",
        feedback_type=FeedbackType.IMPORTANT,
        was_interrupted=True,
        message_category="financial",
        user_response_time_seconds=15.5,
        feedback_reason="This was indeed an important financial notification",
    )

    print(f"Success: {success}")
    print(f"Message: {message}")

    # Example 2: Process multiple feedbacks
    print("\n2. Processing multiple feedbacks...")
    print("-" * 80)

    feedbacks = [
        {
            "message_id": "msg-12346",
            "sender_phone": "5511987654321",
            "sender_name": "Maria Silva",
            "feedback_type": FeedbackType.IMPORTANT,
            "was_interrupted": True,
            "category": "financial",
            "response_time": 20.0,
        },
        {
            "message_id": "msg-12347",
            "sender_phone": "5511987654321",
            "sender_name": "Maria Silva",
            "feedback_type": FeedbackType.NOT_IMPORTANT,
            "was_interrupted": False,
            "category": "marketing",
            "response_time": None,
        },
        {
            "message_id": "msg-12348",
            "sender_phone": "5511912345678",
            "sender_name": "João Santos",
            "feedback_type": FeedbackType.IMPORTANT,
            "was_interrupted": False,  # System missed this one
            "category": "security",
            "response_time": 5.0,
        },
    ]

    for feedback in feedbacks:
        success, msg = await learning_agent.process_feedback(
            tenant_id="tenant-001",
            user_id="user-001",
            message_id=feedback["message_id"],
            sender_phone=feedback["sender_phone"],
            sender_name=feedback["sender_name"],
            feedback_type=feedback["feedback_type"],
            was_interrupted=feedback["was_interrupted"],
            message_category=feedback["category"],
            user_response_time_seconds=feedback["response_time"],
        )
        print(f"  {feedback['message_id']}: {msg}")

    # Example 3: Get statistics for a sender
    print("\n3. Retrieving sender statistics...")
    print("-" * 80)

    stats = await learning_agent.get_sender_statistics(
        tenant_id="tenant-001",
        user_id="user-001",
        sender_phone="5511987654321",
    )

    if stats:
        print(f"Sender: 5511987654321 (Maria Silva)")
        print(f"  Total feedback: {stats.get('total_feedback_count', 0)}")
        print(f"  Important: {stats.get('important_count', 0)}")
        print(f"  Not important: {stats.get('not_important_count', 0)}")
        print(f"  Avg response time: {stats.get('avg_response_time_seconds', 0):.1f}s")
    else:
        print("No statistics available yet (expected in test environment)")

    # Example 4: Get historical context for Urgency Agent
    print("\n4. Generating historical context for Urgency Agent...")
    print("-" * 80)

    context = await data_provider.generate_historical_context_prompt(
        tenant_id="tenant-001",
        user_id="user-001",
        sender_phone="5511987654321",
        category="financial",
    )

    print(context if context else "No historical context available (expected in test environment)")

    # Example 5: Get overall performance metrics
    print("\n5. Overall system performance metrics...")
    print("-" * 80)

    metrics = await data_provider.get_performance_metrics(
        tenant_id="tenant-001",
        user_id="user-001",
    )

    if metrics:
        print(f"Total feedback entries: {metrics.get('total_feedback', 0)}")
        print(f"Accuracy: {metrics.get('accuracy', 0):.1%}")
        print(f"Precision: {metrics.get('precision', 0):.1%}")
        print(f"Recall: {metrics.get('recall', 0):.1%}")
        print(f"Correct interrupts: {metrics.get('correct_interrupts', 0)}")
        print(f"Missed urgent: {metrics.get('missed_urgent', 0)}")
    else:
        print("No metrics available (expected in test environment)")

    print("\n" + "=" * 80)
    print("Learning Agent Example Complete")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
