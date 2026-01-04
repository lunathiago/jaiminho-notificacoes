"""Example: SendPulse Adapter Integration

Demonstrates usage of the SendPulse WhatsApp adapter for:
1. Sending urgent notifications
2. Sending daily digests
3. Collecting feedback with interactive buttons
"""

import asyncio
from typing import List

from jaiminho_notificacoes.outbound.sendpulse import (
    SendPulseManager,
    SendPulseButton,
    NotificationType,
    SendPulseResponse
)


# ============================================================================
# Example 1: Sending Urgent Notification
# ============================================================================

async def example_urgent_notification():
    """Send an urgent notification immediately."""
    print("=== Example 1: Urgent Notification ===\n")

    manager = SendPulseManager()

    response = await manager.send_notification(
        tenant_id='acme_corp',
        user_id='user_123',
        content_text='🚨 ALERT: High priority issue detected in production.\nPlease review immediately.',
        message_type=NotificationType.URGENT
    )

    print(f"Success: {response.success}")
    print(f"Message ID: {response.message_id}")
    print(f"Status: {response.status}")
    if response.error:
        print(f"Error: {response.error}")


# ============================================================================
# Example 2: Sending Daily Digest
# ============================================================================

async def example_daily_digest():
    """Send a daily digest with summary."""
    print("\n=== Example 2: Daily Digest ===\n")

    manager = SendPulseManager()

    digest_text = """
📅 Daily Digest - January 15, 2024

📊 Stats:
- New messages: 12
- Urgent items: 2
- Completed tasks: 8

🔔 Urgent:
1. Database migration scheduled for tomorrow
2. Security patch available for review

📝 Recent Activity:
- Team meeting at 3 PM
- Q1 planning session
- New feature deployment

👉 Reply to this message for more details.
    """.strip()

    response = await manager.send_notification(
        tenant_id='acme_corp',
        user_id='user_456',
        content_text=digest_text,
        message_type=NotificationType.DIGEST,
        metadata={
            'digest_date': '2024-01-15',
            'digest_type': 'daily_summary'
        }
    )

    print(f"Digest sent: {response.success}")
    print(f"Message ID: {response.message_id}")


# ============================================================================
# Example 3: Collecting Feedback with Interactive Buttons
# ============================================================================

async def example_feedback_collection():
    """Collect feedback using interactive buttons."""
    print("\n=== Example 3: Feedback Collection ===\n")

    manager = SendPulseManager()

    buttons = [
        SendPulseButton(id='important', title='Important', action='reply'),
        SendPulseButton(id='not_important', title='Not Important', action='reply')
    ]

    response = await manager.send_notification(
        tenant_id='acme_corp',
        user_id='user_789',
        content_text='Was this notification helpful and important to you?',
        message_type=NotificationType.FEEDBACK,
        buttons=buttons,
        metadata={
            'feedback_type': 'notification_quality',
            'notification_id': 'notif_12345'
        }
    )

    print(f"Feedback request sent: {response.success}")
    print(f"Message ID: {response.message_id}")
    print("Awaiting user response...")


# ============================================================================
# Example 4: Batch Sending to Multiple Users
# ============================================================================

async def example_batch_send():
    """Send the same notification to multiple users."""
    print("\n=== Example 4: Batch Send ===\n")

    manager = SendPulseManager()

    user_ids = [
        'user_001',
        'user_002',
        'user_003',
        'user_004',
        'user_005'
    ]

    message_text = """
🎉 System Maintenance Window

We'll be performing scheduled maintenance tomorrow:
⏰ 2:00 AM - 4:00 AM (UTC)

Expected downtime: ~2 hours
Systems affected:
- API endpoints
- Dashboard
- Mobile app

Thank you for your patience!
    """.strip()

    print(f"Sending to {len(user_ids)} users...")

    responses = await manager.send_batch(
        tenant_id='acme_corp',
        user_ids=user_ids,
        content_text=message_text,
        message_type=NotificationType.URGENT
    )

    # Analyze results
    successful = sum(1 for r in responses if r.success)
    failed = len(responses) - successful

    print(f"Total: {len(responses)}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")

    if failed > 0:
        print("\nFailed users:")
        for i, response in enumerate(responses):
            if not response.success:
                print(f"  - user_{i}: {response.error}")


# ============================================================================
# Example 5: Advanced - Conditional Notification
# ============================================================================

async def example_conditional_notification():
    """Send notification with conditional logic."""
    print("\n=== Example 5: Conditional Notification ===\n")

    manager = SendPulseManager()

    # Example data from urgency system
    urgency_score = 0.85  # 0-1 scale
    message_category = 'system_alert'
    sender_reliability = 0.95

    # Determine notification type based on urgency
    if urgency_score > 0.8:
        notification_type = NotificationType.URGENT
        prefix = "🚨 HIGH PRIORITY:"
    elif urgency_score > 0.5:
        notification_type = NotificationType.URGENT
        prefix = "⚠️ MEDIUM PRIORITY:"
    else:
        notification_type = NotificationType.DIGEST
        prefix = "ℹ️ FYI:"

    content = f"{prefix} System notification\nUrgency: {urgency_score * 100:.0f}%"

    response = await manager.send_notification(
        tenant_id='acme_corp',
        user_id='user_vip_001',
        content_text=content,
        message_type=notification_type,
        metadata={
            'urgency_score': urgency_score,
            'category': message_category,
            'sender_reliability': sender_reliability
        }
    )

    print(f"Notification type: {notification_type.value}")
    print(f"Urgency score: {urgency_score}")
    print(f"Sent: {response.success}")


# ============================================================================
# Example 6: Integration with Learning Agent
# ============================================================================

async def example_learning_agent_integration():
    """Collect feedback to feed Learning Agent."""
    print("\n=== Example 6: Learning Agent Integration ===\n")

    manager = SendPulseManager()

    # Send message with feedback buttons for Learning Agent
    buttons = [
        SendPulseButton(
            id='is_important',
            title='Important',
            action='reply'
        ),
        SendPulseButton(
            id='not_important',
            title='Not Important',
            action='reply'
        )
    ]

    message = """
📬 Message from John Smith

Subject: Q1 Budget Review

Dear team, please review the attached budget proposal for Q1 review...

Is this message important to you?
    """.strip()

    response = await manager.send_notification(
        tenant_id='acme_corp',
        user_id='user_manager_001',
        content_text=message,
        message_type=NotificationType.FEEDBACK,
        buttons=buttons,
        metadata={
            'sender': 'john.smith@acme.com',
            'subject': 'Q1 Budget Review',
            'message_source': 'email_gateway',
            'feed_to_learning_agent': True
        }
    )

    print(f"Message with feedback buttons sent: {response.success}")
    print(f"Message ID: {response.message_id}")
    print("Response will be used to train Learning Agent")


# ============================================================================
# Example 7: Error Handling
# ============================================================================

async def example_error_handling():
    """Demonstrate error handling."""
    print("\n=== Example 7: Error Handling ===\n")

    manager = SendPulseManager()

    test_cases = [
        {
            'name': 'Valid message',
            'params': {
                'tenant_id': 'acme_corp',
                'user_id': 'user_valid',
                'content_text': 'Valid message'
            },
            'expect_error': False
        },
        {
            'name': 'Empty content',
            'params': {
                'tenant_id': 'acme_corp',
                'user_id': 'user_test',
                'content_text': ''
            },
            'expect_error': True
        },
        {
            'name': 'Text too long (>4096)',
            'params': {
                'tenant_id': 'acme_corp',
                'user_id': 'user_test',
                'content_text': 'x' * 5000
            },
            'expect_error': True
        },
        {
            'name': 'Missing user_id for phone resolution',
            'params': {
                'tenant_id': 'acme_corp',
                'user_id': '',  # Empty user_id prevents phone resolution
                'content_text': 'Test'
            },
            'expect_error': True
        },
    ]

    for test in test_cases:
        print(f"Testing: {test['name']}")
        response = await manager.send_notification(**test['params'])

        if test['expect_error']:
            assert not response.success, "Should have failed"
            print(f"  ✓ Error (expected): {response.error}")
        else:
            if not response.success:
                print(f"  ! Note: {response.error}")
            else:
                print(f"  ✓ Success")

        print()


# ============================================================================
# Example 8: Performance - Batch Processing
# ============================================================================

async def example_batch_performance():
    """Demonstrate batch processing performance."""
    print("\n=== Example 8: Batch Processing ===\n")

    manager = SendPulseManager()

    # Simulate large batch
    user_ids = [f'user_{i:05d}' for i in range(100)]

    message = "Daily digest summary"

    import time
    start_time = time.time()

    responses = await manager.send_batch(
        tenant_id='acme_corp',
        user_ids=user_ids,
        content_text=message,
        message_type=NotificationType.DIGEST
    )

    elapsed = time.time() - start_time

    successful = sum(1 for r in responses if r.success)

    print(f"Batch size: {len(user_ids)}")
    print(f"Successful: {successful}")
    print(f"Time elapsed: {elapsed:.2f}s")
    print(f"Rate: {len(user_ids) / elapsed:.1f} msgs/sec")


# ============================================================================
# Main: Run All Examples
# ============================================================================

async def main():
    """Run all examples."""
    print("=" * 70)
    print("SendPulse Adapter - Usage Examples")
    print("=" * 70)

    # Note: Some examples may fail if SendPulse credentials are not configured
    # They demonstrate the correct usage patterns

    try:
        await example_urgent_notification()
        await example_daily_digest()
        await example_feedback_collection()
        await example_batch_send()
        await example_conditional_notification()
        await example_learning_agent_integration()
        await example_error_handling()
        await example_batch_performance()

    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nNote: Ensure SendPulse credentials are configured in Secrets Manager")
        print("Environment variable: SENDPULSE_SECRET_ARN")


if __name__ == '__main__':
    asyncio.run(main())
