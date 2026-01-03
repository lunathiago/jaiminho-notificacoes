"""Lambda handler: Process user feedback on message urgency.

Webhook endpoint for receiving user feedback:
- POST /feedback with message ID and feedback type
- Updates interruption statistics
- Maintains audit trail
"""

import json
import os
from typing import Any, Dict, Optional
import boto3
from pydantic import ValidationError, BaseModel, Field

from ..core.logger import get_logger
from ..core.tenant import TenantIsolationMiddleware
from ..processing.learning_agent import LearningAgent, FeedbackType

logger = get_logger(__name__)

# Initialize AWS clients
cloudwatch = boto3.client('cloudwatch')

# Environment variables
LEARNING_AGENT_ENABLED = os.getenv('LEARNING_AGENT_ENABLED', 'true').lower() == 'true'


class FeedbackRequest(BaseModel):
    """Feedback webhook request schema."""
    tenant_id: Optional[str] = Field(None, min_length=1)
    wapi_instance_id: str = Field(..., min_length=1)
    message_id: str = Field(..., min_length=1)
    sender_phone: str = Field(..., pattern="^[0-9]{10,15}$")
    sender_name: Optional[str] = None
    feedback_type: str = Field(..., pattern="^(important|not_important)$")
    was_interrupted: bool
    message_category: Optional[str] = None
    user_response_time_seconds: Optional[float] = Field(None, ge=0)
    feedback_reason: Optional[str] = None


async def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for processing user feedback.

    Expected event structure:
    {
        "body": {
            "tenant_id": "tenant-123",
            "wapi_instance_id": "instance-abc",
            "message_id": "msg-789",
            "sender_phone": "5511999999999",
            "sender_name": "João",
            "feedback_type": "important" or "not_important",
            "was_interrupted": true/false,
            "message_category": "financial" (optional),
            "user_response_time_seconds": 45.5 (optional),
            "feedback_reason": "User provided reason" (optional)
        }
    }

    Returns:
    {
        "statusCode": 200 or 400 or 500,
        "body": {
            "success": bool,
            "message": str,
            "feedback_id": str (if successful)
        }
    }
    """
    try:
        if not LEARNING_AGENT_ENABLED:
            logger.info("Learning agent is disabled")
            return {
                "statusCode": 501,
                "body": json.dumps({
                    "success": False,
                    "message": "Learning agent is disabled"
                })
            }

        # Parse request
        try:
            if isinstance(event.get('body'), str):
                body = json.loads(event['body'])
            else:
                body = event.get('body', event)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in request body: {e}")
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "success": False,
                    "message": "Invalid request body"
                })
            }

        # Validate request
        try:
            request = FeedbackRequest(**body)
        except ValidationError as e:
            logger.error(f"Request validation failed: {e}")
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "success": False,
                    "message": f"Invalid request: {str(e)}"
                })
            }

        # Validate tenant context
        middleware = TenantIsolationMiddleware()
        tenant_payload = {'tenant_id': request.tenant_id} if request.tenant_id else None
        tenant_context, validation_errors = await middleware.validate_and_resolve(
            instance_id=request.wapi_instance_id,
            sender_phone=request.sender_phone,
            payload=tenant_payload
        )

        if not tenant_context:
            logger.error(
                "Tenant context resolution failed",
                instance_id=request.wapi_instance_id,
                validation_errors=validation_errors
            )
            return {
                "statusCode": 403,
                "body": json.dumps({
                    "success": False,
                    "message": "Tenant validation failed"
                })
            }

        if request.tenant_id and request.tenant_id != tenant_context.tenant_id:
            logger.error(
                "Tenant mismatch between payload and resolved context",
                payload_tenant=request.tenant_id,
                resolved_tenant=tenant_context.tenant_id,
                instance_id=tenant_context.instance_id
            )
            return {
                "statusCode": 403,
                "body": json.dumps({
                    "success": False,
                    "message": "Tenant mismatch"
                })
            }

        logger.set_context(
            tenant_id=tenant_context.tenant_id,
            user_id=tenant_context.user_id,
            instance_id=tenant_context.instance_id
        )

        # Process feedback
        learning_agent = LearningAgent()

        feedback_type_enum = (
            FeedbackType.IMPORTANT
            if request.feedback_type == "important"
            else FeedbackType.NOT_IMPORTANT
        )

        success, message = await learning_agent.process_feedback(
            tenant_context=tenant_context,
            message_id=request.message_id,
            sender_phone=request.sender_phone,
            sender_name=request.sender_name,
            feedback_type=feedback_type_enum,
            was_interrupted=request.was_interrupted,
            message_category=request.message_category,
            user_response_time_seconds=request.user_response_time_seconds,
            feedback_reason=request.feedback_reason,
        )

        if not success:
            logger.warning(f"Feedback processing failed: {message}")
            return {
                "statusCode": 500,
                "body": json.dumps({
                    "success": False,
                    "message": message
                })
            }

        # Emit CloudWatch metric
        try:
            cloudwatch.put_metric_data(
                Namespace='JaininhoNotificacoes/LearningAgent',
                MetricData=[
                    {
                        'MetricName': 'FeedbackReceived',
                        'Value': 1,
                        'Unit': 'Count',
                        'Dimensions': [
                            {'Name': 'TenantId', 'Value': tenant_context.tenant_id},
                            {'Name': 'FeedbackType', 'Value': request.feedback_type},
                            {'Name': 'WasInterrupted', 'Value': str(request.was_interrupted)},
                        ]
                    }
                ]
            )
        except Exception as e:
            logger.warning(f"Failed to emit CloudWatch metric: {e}")

        logger.info(
            "Feedback processed successfully",
            tenant_id=tenant_context.tenant_id,
            user_id=tenant_context.user_id,
            feedback_type=request.feedback_type
        )

        return {
            "statusCode": 200,
            "body": json.dumps({
                "success": True,
                "message": message,
                "feedback_id": message.split()[-1]  # Extract feedback_id from message
            })
        }

    except Exception as e:
        logger.error(f"Unhandled error in feedback handler: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({
                "success": False,
                "message": "Internal server error"
            })
        }
    finally:
        logger.clear_context()


# For local testing
if __name__ == "__main__":
    import asyncio

    test_event = {
        "body": {
            "tenant_id": "tenant-123",
            "wapi_instance_id": "instance-abc",
            "message_id": "msg-789",
            "sender_phone": "5511999999999",
            "sender_name": "João Silva",
            "feedback_type": "important",
            "was_interrupted": True,
            "message_category": "financial",
            "user_response_time_seconds": 30.5,
            "feedback_reason": "Realmente era importante"
        }
    }

    result = asyncio.run(handler(test_event, None))
    print(json.dumps(result, indent=2))
