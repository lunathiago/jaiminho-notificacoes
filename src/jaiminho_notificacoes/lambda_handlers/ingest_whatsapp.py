"""Lambda handler: WhatsApp message ingestion from W-API.

This is a SECURITY-CRITICAL component that:
1. Receives webhooks from W-API
2. Validates instance_id authenticity
3. Resolves user_id internally (NEVER trusts payload)
4. Validates phone number ownership
5. Normalizes messages to unified schema
6. Forwards to decision engine
7. Rejects and logs invalid/cross-tenant payloads
"""

import json
import os
import traceback
from typing import Any, Dict, Optional
import boto3
from pydantic import ValidationError

from ..core.logger import get_logger
from ..core.tenant import TenantIsolationMiddleware
from ..ingestion.normalizer import MessageNormalizer
from ..persistence.models import WAPIWebhookEvent, NormalizedMessage

logger = get_logger(__name__)

# Initialize AWS clients
sqs_client = boto3.client('sqs')
dynamodb = boto3.resource('dynamodb')

# Environment variables
SQS_QUEUE_URL = os.getenv('SQS_QUEUE_URL')
DYNAMODB_MESSAGES_TABLE = os.getenv('DYNAMODB_MESSAGES_TABLE')


class WebhookSecurityValidator:
    """Validates webhook authenticity and security for W-API only."""
    
    def __init__(self):
        self.middleware = TenantIsolationMiddleware()
    
    async def validate_request(
        self,
        event: Dict[str, Any]
    ) -> tuple[Optional[WAPIWebhookEvent], Optional[str]]:
        """
        Validate incoming W-API webhook request.
        
        Security checks:
        - Validates JSON structure
        - Enforces W-API schema (instance, event, data required)
        - Rejects non-W-API payloads
        
        Returns:
            (validated_event, error_message) tuple
        """
        # Extract body
        body = self._extract_body(event)
        if not body:
            logger.security_event(
                event_type='invalid_request',
                severity='medium',
                message='Empty or invalid request body'
            )
            return None, "Empty or invalid request body"
        
        # Parse JSON
        try:
            payload = json.loads(body) if isinstance(body, str) else body
        except json.JSONDecodeError as e:
            logger.security_validation_failed(
                reason='Invalid JSON payload',
                details={'error': str(e), 'error_type': 'json_decode'}
            )
            return None, "Invalid JSON format"
        
        # Validate against W-API schema
        try:
            webhook_event = WAPIWebhookEvent(**payload)
        except ValidationError as e:
            logger.security_validation_failed(
                reason='W-API schema validation failed',
                details={
                    'errors': e.errors(),
                    'payload_keys': list(payload.keys()),
                    'validation_error': 'payload does not conform to W-API schema'
                }
            )
            return None, "Invalid W-API payload format"
        
        return webhook_event, None
    
    @staticmethod
    def _extract_body(event: Dict[str, Any]) -> Optional[str]:
        """Extract body from Lambda event."""
        # API Gateway HTTP API format
        if 'body' in event:
            return event['body']
        
        # Direct invocation
        if isinstance(event, dict) and 'instance' in event:
            return json.dumps(event)
        
        return None


class MessageIngestionHandler:
    """Main handler for message ingestion."""
    
    def __init__(self):
        self.validator = WebhookSecurityValidator()
        self.middleware = TenantIsolationMiddleware()
        self.normalizer = MessageNormalizer()
    
    async def process_webhook(
        self,
        event: Dict[str, Any],
        context: Any
    ) -> Dict[str, Any]:
        """
        Main W-API webhook processing logic.
        
        ✅ W-API ONLY - No Evolution API support
        
        Security validation pipeline (in order):
        1. Validate webhook structure (W-API schema)
        2. Validate wapi_instance_id authenticity (DynamoDB lookup)
        3. Resolve tenant_id and user_id INTERNALLY (never from payload)
        4. Validate phone ownership (sender phone matches instance)
        5. Detect cross-tenant access attempts
        6. Normalize message to unified schema
        7. Forward to processing queue
        
        Security guarantees:
        ✓ Unknown or inactive wapi_instance_id → 403 Forbidden
        ✓ Sender phone not owned by instance → 403 Forbidden
        ✓ Cross-tenant attempt detected → 403 Forbidden
        ✓ All rejections logged and audited
        
        Args:
            event: Lambda event (API Gateway HTTP API format)
            context: Lambda context
            
        Returns:
            HTTP response dict
        """
        request_id = context.request_id if context else 'unknown'
        logger.set_context(request_id=request_id)
        
        try:
            # Step 1: Validate webhook structure
            logger.info("Processing webhook request")
            webhook_event, error = await self.validator.validate_request(event)
            
            if error or not webhook_event:
                return self._error_response(
                    status_code=400,
                    message=error or "Invalid webhook format"
                )
            
            # Check if event type should be processed
            if not self.normalizer.should_process_event(webhook_event.event):
                logger.info(
                    f"Ignoring event type: {webhook_event.event}",
                    event_type=webhook_event.event
                )
                return self._success_response(message="Event ignored")
            
            # Extract W-API instance identifier and API key
            wapi_instance_id = webhook_event.instance
            api_key = webhook_event.apikey
            sender_remote_jid = webhook_event.data.key.remoteJid
            
            logger.info(
                f"Processing W-API event: {webhook_event.event}",
                instance_id=wapi_instance_id,
                event_type=webhook_event.event,
                sender=sender_remote_jid
            )
            
            # Step 2-5: Complete W-API security validation pipeline
            # Validates: instance_id authenticity, API key, status, phone ownership, cross-tenant attempts
            tenant_context, validation_errors = await self.middleware.validate_and_resolve(
                instance_id=wapi_instance_id,
                api_key=api_key,
                sender_phone=sender_remote_jid,
                payload=webhook_event.dict()
            )
            
            if validation_errors or not tenant_context:
                # Audit log all rejections with detailed context
                logger.security_validation_failed(
                    reason='W-API instance validation failed - webhook rejected',
                    instance_id=wapi_instance_id,
                    details={
                        'errors': validation_errors,
                        'sender_phone': sender_remote_jid,
                        'validation_failures': list(validation_errors.keys()) if validation_errors else []
                    }
                )
                return self._error_response(
                    status_code=403,
                    message="Unauthorized: Invalid or inactive W-API instance"
                )
            
            # Set tenant context for all subsequent logs
            # user_id has been verified and resolved internally - not from payload
            logger.set_context(
                tenant_id=tenant_context.tenant_id,
                user_id=tenant_context.user_id,
                instance_id=wapi_instance_id
            )
            
            logger.info(
                f"W-API instance validated successfully - user_id resolved internally",
                user_id=tenant_context.user_id,
                tenant_id=tenant_context.tenant_id
            )
            
            # Step 6: Normalize message
            # All security validations passed; instance and phone verified
            validation_status = {
                'instance_verified': True,       # Verified via resolve_from_instance
                'tenant_resolved': True,         # Resolved from instance mapping
                'phone_verified': True           # Verified via validate_phone_ownership
            }
            
            normalized_message = self.normalizer.normalize(
                event=webhook_event,
                tenant_context=tenant_context,
                validation_status=validation_status
            )
            
            if not normalized_message:
                logger.error("Message normalization failed")
                return self._error_response(
                    status_code=500,
                    message="Failed to normalize message"
                )
            
            # Step 7: Forward to processing queue
            success = await self._forward_to_queue(normalized_message)
            
            if not success:
                logger.error("Failed to forward message to queue")
                return self._error_response(
                    status_code=500,
                    message="Failed to queue message"
                )
            
            # Log successful processing with W-API source metadata
            logger.message_processed(
                message_id=normalized_message.message_id,
                tenant_id=tenant_context.tenant_id,
                user_id=tenant_context.user_id,
                message_type=normalized_message.message_type.value,
                source='wapi',
                wapi_instance_id=wapi_instance_id
            )
            
            return self._success_response(
                message="Message processed successfully",
                data={'message_id': normalized_message.message_id}
            )
            
        except Exception as e:
            logger.critical(
                f"Unexpected error in webhook handler: {str(e)}",
                details={
                    'error_type': type(e).__name__,
                    'traceback': traceback.format_exc()
                }
            )
            return self._error_response(
                status_code=500,
                message="Internal server error"
            )
        finally:
            logger.clear_context()
    
    async def _forward_to_queue(self, message: NormalizedMessage) -> bool:
        """Forward normalized message to SQS for processing."""
        if not SQS_QUEUE_URL:
            logger.error("SQS_QUEUE_URL not configured")
            return False
        
        try:
            # Serialize message
            message_body = message.json()
            
            # Send to SQS
            response = sqs_client.send_message(
                QueueUrl=SQS_QUEUE_URL,
                MessageBody=message_body,
                MessageAttributes={
                    'tenant_id': {
                        'StringValue': message.tenant_id,
                        'DataType': 'String'
                    },
                    'user_id': {
                        'StringValue': message.user_id,
                        'DataType': 'String'
                    },
                    'message_type': {
                        'StringValue': message.message_type.value,
                        'DataType': 'String'
                    }
                }
            )
            
            logger.info(
                f"Message forwarded to SQS: {response['MessageId']}",
                message_id=message.message_id,
                sqs_message_id=response['MessageId']
            )
            
            return True
            
        except Exception as e:
            logger.error(
                f"Failed to send message to SQS: {str(e)}",
                message_id=message.message_id,
                details={'error_type': type(e).__name__}
            )
            return False
    
    @staticmethod
    def _success_response(
        message: str,
        data: Optional[Dict] = None,
        status_code: int = 200
    ) -> Dict[str, Any]:
        """Create success response."""
        body = {
            'success': True,
            'message': message
        }
        if data:
            body['data'] = data
        
        return {
            'statusCode': status_code,
            'headers': {
                'Content-Type': 'application/json',
                'X-Content-Type-Options': 'nosniff',
                'X-Frame-Options': 'DENY'
            },
            'body': json.dumps(body)
        }
    
    @staticmethod
    def _error_response(
        status_code: int,
        message: str,
        details: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Create error response."""
        body = {
            'success': False,
            'error': message
        }
        if details and os.getenv('ENVIRONMENT') != 'prod':
            body['details'] = details
        
        return {
            'statusCode': status_code,
            'headers': {
                'Content-Type': 'application/json',
                'X-Content-Type-Options': 'nosniff',
                'X-Frame-Options': 'DENY'
            },
            'body': json.dumps(body)
        }


# Lambda handler entry point
handler_instance = None


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler entry point.
    
    This function receives webhooks from W-API and processes them
    through the complete security validation pipeline.
    
    Args:
        event: Lambda event (API Gateway HTTP API format)
        context: Lambda context
        
    Returns:
        HTTP response dict
    """
    global handler_instance
    
    if handler_instance is None:
        handler_instance = MessageIngestionHandler()
    
    # Use asyncio for async operations
    import asyncio
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(
        handler_instance.process_webhook(event, context)
    )


# Health check handler
def health_check(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Health check endpoint."""
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({
            'status': 'healthy',
            'service': 'jaiminho-webhook-ingestion',
            'version': '1.0.0'
        })
    }

