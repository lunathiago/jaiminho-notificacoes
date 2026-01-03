"""Lambda handler for processing SendPulse feedback webhooks.

This handler:
1. Receives webhook events from SendPulse
2. Validates and parses button responses
3. Routes to FeedbackHandler for processing
4. Updates Learning Agent statistics
5. Returns 200 OK for acknowledgment
"""

import json
import asyncio
from typing import Any, Dict

from jaiminho_notificacoes.core.logger import TenantContextLogger
from jaiminho_notificacoes.processing.feedback_handler import get_feedback_handler


logger = TenantContextLogger(__name__)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Process SendPulse feedback webhook.

    Event structure (from SendPulse):
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
            "user_id": "user_1",
            "tenant_id": "tenant_1"
        }
    }

    Args:
        event: Lambda event
        context: Lambda context

    Returns:
        HTTP response
    """
    try:
        logger.info(
            "Received feedback webhook",
            event_type=event.get('event'),
            has_metadata='metadata' in event
        )

        # Parse body if needed
        if isinstance(event.get('body'), str):
            body = json.loads(event['body'])
        else:
            body = event

        # Process feedback
        result = asyncio.run(
            get_feedback_handler().handle_webhook(body)
        )

        # Log result
        if result.success:
            logger.info(
                "Feedback processed successfully",
                feedback_id=result.feedback_id,
                feedback_type=result.feedback_type,
                processing_time_ms=result.processing_time_ms
            )

            return {
                'statusCode': 200,
                'body': json.dumps({
                    'status': 'success',
                    'feedback_id': result.feedback_id,
                    'processing_time_ms': result.processing_time_ms,
                    'statistics_updated': result.statistics_updated
                })
            }
        else:
            logger.warning(
                "Feedback processing failed",
                error=result.error
            )

            return {
                'statusCode': 400,
                'body': json.dumps({
                    'status': 'error',
                    'error': result.error,
                    'processing_time_ms': result.processing_time_ms
                })
            }

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in webhook: {e}")
        return {
            'statusCode': 400,
            'body': json.dumps({
                'status': 'error',
                'error': 'Invalid JSON format'
            })
        }

    except Exception as e:
        logger.error(f"Unhandled error in feedback handler: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'status': 'error',
                'error': f'Internal server error: {str(e)}'
            })
        }
