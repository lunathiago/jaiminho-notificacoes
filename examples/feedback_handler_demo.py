"""Examples of using the SendPulse Feedback Handler.

Demonstrates:
1. Processing webhook events
2. Validating feedback
3. Batch processing
4. Integration with Learning Agent
5. Metric emission
"""

import asyncio
import json
from datetime import datetime

from jaiminho_notificacoes.processing.feedback_handler import (
    get_feedback_handler,
    SendPulseWebhookValidator,
    UserFeedbackProcessor,
)


# Example 1: Process a Single Feedback Event
async def example_single_feedback():
    """Process a single button click feedback."""
    print("=" * 60)
    print("Example 1: Process Single Feedback Event")
    print("=" * 60)

    # Webhook event from SendPulse
    webhook_event = {
        'event': 'message.reaction',
        'recipient': '+5548999887766',
        'message_id': 'sendpulse_msg_abc123',
        'button_reply': {
            'id': 'important',
            'title': '🔴 Important'
        },
        'timestamp': int(datetime.utcnow().timestamp()),
        'metadata': {
            'message_id': 'jaiminho_notif_456',
            'user_id': 'user_alice',
            'tenant_id': 'company_acme'
        }
    }

    print("\nWebhook Event:")
    print(json.dumps(webhook_event, indent=2))

    # Get handler
    handler = get_feedback_handler()

    # Process feedback
    result = await handler.handle_webhook(webhook_event)

    print("\nProcessing Result:")
    print(f"  Success: {result.success}")
    print(f"  Feedback ID: {result.feedback_id}")
    print(f"  Feedback Type: {result.feedback_type}")
    print(f"  Message ID: {result.message_id}")
    print(f"  User ID: {result.user_id}")
    print(f"  Statistics Updated: {result.statistics_updated}")
    print(f"  Processing Time: {result.processing_time_ms:.2f}ms")

    if not result.success:
        print(f"  Error: {result.error}")

    print()


# Example 2: Validate Multiple Button Types
async def example_validation():
    """Validate different button types."""
    print("=" * 60)
    print("Example 2: Webhook Validation")
    print("=" * 60)

    validator = SendPulseWebhookValidator()

    # Valid event
    valid_event = {
        'event': 'message.reaction',
        'recipient': '+5548999887766',
        'message_id': 'sendpulse_msg_xyz789',
        'button_reply': {
            'id': 'not_important',
            'title': '⚪ Not Important'
        },
        'timestamp': int(datetime.utcnow().timestamp()),
        'metadata': {
            'message_id': 'jaiminho_notif_789',
            'user_id': 'user_bob',
            'tenant_id': 'company_beta'
        }
    }

    print("\nValidating Valid Event...")
    valid, error = validator.validate_event(valid_event)
    print(f"  Valid: {valid}")
    if not valid:
        print(f"  Error: {error}")

    # Invalid event (missing metadata)
    invalid_event = {
        'event': 'message.reaction',
        'recipient': '+5548999887766',
        'message_id': 'sendpulse_msg_xyz789',
        'button_reply': {
            'id': 'important',
            'title': 'Important'
        },
        'timestamp': int(datetime.utcnow().timestamp())
        # Missing metadata!
    }

    print("\nValidating Invalid Event (missing metadata)...")
    valid, error = validator.validate_event(invalid_event)
    print(f"  Valid: {valid}")
    print(f"  Error: {error}")

    # Button mapping
    print("\nButton Type Mapping:")
    for button_id in ['important', 'not_important', 'unknown']:
        feedback_type = validator.map_button_to_feedback(button_id)
        print(f"  Button '{button_id}' → {feedback_type}")

    print()


# Example 3: Batch Process Multiple Events
async def example_batch_processing():
    """Process multiple feedback events in batch."""
    print("=" * 60)
    print("Example 3: Batch Processing")
    print("=" * 60)

    handler = get_feedback_handler()

    # Create 5 webhook events
    events = []
    for i in range(5):
        event = {
            'event': 'message.reaction',
            'recipient': f'+554899988776{i}',
            'message_id': f'sendpulse_msg_{i}',
            'button_reply': {
                'id': 'important' if i % 2 == 0 else 'not_important',
                'title': 'Important' if i % 2 == 0 else 'Not Important'
            },
            'timestamp': int(datetime.utcnow().timestamp()) + i,
            'metadata': {
                'message_id': f'jaiminho_notif_{i}',
                'user_id': f'user_{i}',
                'tenant_id': 'company_acme'
            }
        }
        events.append(event)

    print(f"\nProcessing {len(events)} webhook events...\n")

    # Process batch
    results = await handler.handle_batch_webhooks(events)

    # Summary
    successful = sum(1 for r in results if r.success)
    failed = len(results) - successful

    print(f"Results Summary:")
    print(f"  Total: {len(results)}")
    print(f"  Successful: {successful}")
    print(f"  Failed: {failed}")

    print("\nDetailed Results:")
    for i, result in enumerate(results):
        status = "✅" if result.success else "❌"
        print(f"  [{status}] Event {i}:")
        print(f"      Feedback ID: {result.feedback_id}")
        print(f"      Type: {result.feedback_type}")
        print(f"      Time: {result.processing_time_ms:.2f}ms")

        if not result.success:
            print(f"      Error: {result.error}")

    print()


# Example 4: Error Handling
async def example_error_handling():
    """Demonstrate error handling."""
    print("=" * 60)
    print("Example 4: Error Handling")
    print("=" * 60)

    processor = UserFeedbackProcessor()

    # Test 1: Missing required field
    print("\nTest 1: Missing Required Field")
    incomplete_event = {
        'event': 'message.reaction',
        # Missing most fields
    }

    result = await processor.process_feedback(incomplete_event)
    print(f"  Success: {result.success}")
    print(f"  Error: {result.error}")

    # Test 2: Invalid button type
    print("\nTest 2: Invalid Button Type")
    invalid_button_event = {
        'event': 'message.reaction',
        'recipient': '+5548999887766',
        'message_id': 'sendpulse_msg_test',
        'button_reply': {
            'id': 'custom_button',  # Not a valid type!
            'title': 'Custom'
        },
        'timestamp': int(datetime.utcnow().timestamp()),
        'metadata': {
            'message_id': 'jaiminho_notif_test',
            'user_id': 'user_test',
            'tenant_id': 'company_test'
        }
    }

    result = await processor.process_feedback(invalid_button_event)
    print(f"  Success: {result.success}")
    print(f"  Error: {result.error}")

    # Test 3: Invalid timestamp
    print("\nTest 3: Invalid Timestamp")
    invalid_timestamp_event = {
        'event': 'message.reaction',
        'recipient': '+5548999887766',
        'message_id': 'sendpulse_msg_test',
        'button_reply': {
            'id': 'important',
            'title': 'Important'
        },
        'timestamp': 0,  # Invalid!
        'metadata': {
            'message_id': 'jaiminho_notif_test',
            'user_id': 'user_test',
            'tenant_id': 'company_test'
        }
    }

    result = await processor.process_feedback(invalid_timestamp_event)
    print(f"  Success: {result.success}")
    print(f"  Error: {result.error}")

    print()


# Example 5: Response Time Calculation
async def example_response_time():
    """Calculate user response time."""
    print("=" * 60)
    print("Example 5: Response Time Calculation")
    print("=" * 60)

    # Simulate message sent 5 minutes ago
    now = datetime.utcnow()
    sent_dt = now.replace(minute=now.minute - 5)
    sent_at = sent_dt.isoformat()

    response_timestamp = int(now.timestamp())

    response_time = UserFeedbackProcessor._calculate_response_time(
        sent_at,
        response_timestamp
    )

    print(f"\nMessage sent: {sent_at}")
    print(f"Response at: {now.isoformat()}")
    print(f"Response time: {response_time:.0f} seconds ({response_time / 60:.1f} minutes)")

    print()


# Example 6: Webhook Parsing from API Gateway
async def example_api_gateway_webhook():
    """Process webhook from API Gateway."""
    print("=" * 60)
    print("Example 6: API Gateway Webhook")
    print("=" * 60)

    # Event from API Gateway
    api_gateway_event = {
        'resource': '/feedback/webhook',
        'httpMethod': 'POST',
        'body': json.dumps({
            'event': 'message.reaction',
            'recipient': '+5548999887766',
            'message_id': 'sendpulse_msg_gateway',
            'button_reply': {
                'id': 'important',
                'title': '🔴 Important'
            },
            'timestamp': int(datetime.utcnow().timestamp()),
            'metadata': {
                'message_id': 'jaiminho_notif_gateway',
                'user_id': 'user_gateway',
                'tenant_id': 'company_gateway'
            }
        }),
        'headers': {
            'Content-Type': 'application/json'
        }
    }

    print("\nAPI Gateway Event (as from Lambda):")
    print(f"  Resource: {api_gateway_event['resource']}")
    print(f"  Method: {api_gateway_event['httpMethod']}")
    print(f"  Body: {api_gateway_event['body'][:50]}...")

    # Parse body
    body = json.loads(api_gateway_event['body'])

    # Process
    handler = get_feedback_handler()
    result = await handler.handle_webhook(body)

    print("\nLambda Response:")
    print(f"  Status Code: 200 (if successful) or 400/500 (if error)")
    print(f"  Response Body:")
    print(f"    - status: {'success' if result.success else 'error'}")
    print(f"    - feedback_id: {result.feedback_id}")
    print(f"    - processing_time_ms: {result.processing_time_ms:.2f}")

    print()


# Example 7: Multi-Tenant Feedback
async def example_multi_tenant():
    """Process feedback from multiple tenants."""
    print("=" * 60)
    print("Example 7: Multi-Tenant Feedback")
    print("=" * 60)

    handler = get_feedback_handler()

    # Feedback from different tenants
    tenants = ['company_acme', 'company_beta', 'company_gamma']
    results_by_tenant = {}

    for tenant_id in tenants:
        event = {
            'event': 'message.reaction',
            'recipient': '+5548999887766',
            'message_id': f'sendpulse_msg_{tenant_id}',
            'button_reply': {
                'id': 'important',
                'title': 'Important'
            },
            'timestamp': int(datetime.utcnow().timestamp()),
            'metadata': {
                'message_id': f'jaiminho_notif_{tenant_id}',
                'user_id': f'user_{tenant_id}',
                'tenant_id': tenant_id
            }
        }

        result = await handler.handle_webhook(event)
        results_by_tenant[tenant_id] = result

    print("\nFeedback Processed by Tenant:")
    for tenant_id, result in results_by_tenant.items():
        status = "✅" if result.success else "❌"
        print(f"  [{status}] {tenant_id}: {result.feedback_id}")

    print()


# Main runner
async def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("SendPulse Feedback Handler Examples")
    print("=" * 60 + "\n")

    try:
        await example_single_feedback()
        await example_validation()
        await example_batch_processing()
        await example_error_handling()
        await example_response_time()
        await example_api_gateway_webhook()
        await example_multi_tenant()

        print("=" * 60)
        print("All Examples Completed Successfully!")
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"\n❌ Error running examples: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())
