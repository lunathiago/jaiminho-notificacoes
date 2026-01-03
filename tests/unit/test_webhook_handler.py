"""Unit tests for WhatsApp ingestion Lambda handler."""

import json
import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime

from jaiminho_notificacoes.lambda_handlers.ingest_whatsapp import (
    MessageIngestionHandler,
    WebhookSecurityValidator
)
from jaiminho_notificacoes.core.tenant import TenantContext
from jaiminho_notificacoes.persistence.models import (
    WAPIWebhookEvent,
    NormalizedMessage,
    MessageType
)


@pytest.fixture
def valid_webhook_payload():
    """Valid W-API webhook payload."""
    return {
        "instance": "test-instance-123",
        "event": "messages.upsert",
        "apikey": "test-api-key",
        "data": {
            "key": {
                "remoteJid": "5511999999999@s.whatsapp.net",
                "fromMe": False,
                "id": "3EB0C3A5F2E0F8E0B0F0"
            },
            "message": {
                "conversation": "Test message"
            },
            "messageTimestamp": 1704240000,
            "pushName": "Test User"
        }
    }


@pytest.fixture
def api_gateway_event(valid_webhook_payload):
    """API Gateway event format."""
    return {
        "body": json.dumps(valid_webhook_payload),
        "headers": {
            "Content-Type": "application/json"
        },
        "requestContext": {
            "requestId": "test-request-123"
        }
    }


@pytest.fixture
def lambda_context():
    """Mock Lambda context."""
    context = Mock()
    context.request_id = "test-request-123"
    context.function_name = "test-function"
    return context


@pytest.fixture
def tenant_context():
    """Mock tenant context."""
    return TenantContext(
        tenant_id="tenant-abc-123",
        user_id="user-xyz-456",
        instance_id="test-instance-123",
        phone_number="5511999999999",
        status="active"
    )


class TestWebhookSecurityValidator:
    """Test webhook security validation."""
    
    @pytest.mark.asyncio
    async def test_validate_valid_request(self, api_gateway_event):
        """Test validation of valid webhook request."""
        validator = WebhookSecurityValidator()
        event, error = await validator.validate_request(api_gateway_event)
        
        assert event is not None
        assert error is None
        assert isinstance(event, WAPIWebhookEvent)
        assert event.instance == "test-instance-123"
    
    @pytest.mark.asyncio
    async def test_validate_invalid_json(self):
        """Test validation with invalid JSON."""
        validator = WebhookSecurityValidator()
        event = {"body": "invalid json {"}
        
        webhook_event, error = await validator.validate_request(event)
        
        assert webhook_event is None
        assert "Invalid JSON" in error
    
    @pytest.mark.asyncio
    async def test_validate_missing_required_fields(self):
        """Test validation with missing required fields."""
        validator = WebhookSecurityValidator()
        payload = {
            "instance": "test-instance",
            # Missing 'event' and 'data'
        }
        event = {"body": json.dumps(payload)}
        
        webhook_event, error = await validator.validate_request(event)
        
        assert webhook_event is None
        assert "validation failed" in error.lower()
    
    @pytest.mark.asyncio
    async def test_validate_invalid_event_type(self):
        """Test validation with invalid event type."""
        validator = WebhookSecurityValidator()
        payload = {
            "instance": "test-instance",
            "event": "invalid.event.type",
            "data": {
                "key": {
                    "remoteJid": "5511999999999@s.whatsapp.net",
                    "fromMe": False,
                    "id": "123"
                },
                "message": {}
            }
        }
        event = {"body": json.dumps(payload)}
        
        webhook_event, error = await validator.validate_request(event)
        
        assert webhook_event is None
        assert "validation failed" in error.lower()


class TestMessageIngestionHandler:
    """Test main ingestion handler."""
    
    @pytest.mark.asyncio
    @patch('jaiminho_notificacoes.lambda_handlers.ingest_whatsapp.sqs_client')
    async def test_successful_message_processing(
        self,
        mock_sqs,
        api_gateway_event,
        lambda_context,
        tenant_context
    ):
        """Test successful message processing flow."""
        # Mock SQS send
        mock_sqs.send_message.return_value = {'MessageId': 'sqs-msg-123'}
        
        handler = MessageIngestionHandler()
        
        # Mock middleware validation
        with patch.object(
            handler.middleware,
            'validate_and_resolve',
            new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.return_value = (tenant_context, {})
            
            response = await handler.process_webhook(
                api_gateway_event,
                lambda_context
            )
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['success'] is True
        assert 'message_id' in body['data']
    
    @pytest.mark.asyncio
    async def test_reject_invalid_instance(
        self,
        api_gateway_event,
        lambda_context
    ):
        """Test rejection of invalid instance_id."""
        handler = MessageIngestionHandler()
        
        # Mock middleware to return validation error
        with patch.object(
            handler.middleware,
            'validate_and_resolve',
            new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.return_value = (
                None,
                {'instance_id': 'Invalid or unauthorized instance'}
            )
            
            response = await handler.process_webhook(
                api_gateway_event,
                lambda_context
            )
        
        assert response['statusCode'] == 403
        body = json.loads(response['body'])
        assert body['success'] is False
        assert 'Unauthorized' in body['error']
    
    @pytest.mark.asyncio
    async def test_reject_cross_tenant_attempt(
        self,
        api_gateway_event,
        lambda_context
    ):
        """Test rejection of cross-tenant access attempt."""
        handler = MessageIngestionHandler()
        
        # Mock middleware to return cross-tenant error
        with patch.object(
            handler.middleware,
            'validate_and_resolve',
            new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.return_value = (
                None,
                {'cross_tenant': 'Cross-tenant access attempt detected'}
            )
            
            response = await handler.process_webhook(
                api_gateway_event,
                lambda_context
            )
        
        assert response['statusCode'] == 403
        body = json.loads(response['body'])
        assert 'Cross-tenant' in body['error']
    
    @pytest.mark.asyncio
    async def test_reject_phone_ownership_violation(
        self,
        api_gateway_event,
        lambda_context
    ):
        """Test rejection when phone doesn't belong to instance."""
        handler = MessageIngestionHandler()
        
        # Mock middleware to return phone ownership error
        with patch.object(
            handler.middleware,
            'validate_and_resolve',
            new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.return_value = (
                None,
                {'phone_ownership': 'Phone does not belong to this instance'}
            )
            
            response = await handler.process_webhook(
                api_gateway_event,
                lambda_context
            )
        
        assert response['statusCode'] == 403
        body = json.loads(response['body'])
        assert 'Phone does not belong' in body['error']
    
    @pytest.mark.asyncio
    @patch('jaiminho_notificacoes.lambda_handlers.ingest_whatsapp.sqs_client')
    async def test_handle_sqs_failure(
        self,
        mock_sqs,
        api_gateway_event,
        lambda_context,
        tenant_context
    ):
        """Test handling of SQS send failure."""
        # Mock SQS to raise exception
        mock_sqs.send_message.side_effect = Exception("SQS error")
        
        handler = MessageIngestionHandler()
        
        with patch.object(
            handler.middleware,
            'validate_and_resolve',
            new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.return_value = (tenant_context, {})
            
            response = await handler.process_webhook(
                api_gateway_event,
                lambda_context
            )
        
        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert body['success'] is False
        assert 'Failed to queue' in body['error']
    
    @pytest.mark.asyncio
    async def test_ignore_unsupported_event_types(
        self,
        lambda_context
    ):
        """Test that unsupported event types are ignored."""
        payload = {
            "instance": "test-instance",
            "event": "connection.update",  # Unsupported
            "data": {
                "key": {
                    "remoteJid": "5511999999999@s.whatsapp.net",
                    "fromMe": False,
                    "id": "123"
                },
                "message": {}
            }
        }
        event = {"body": json.dumps(payload)}
        
        handler = MessageIngestionHandler()
        response = await handler.process_webhook(event, lambda_context)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'ignored' in body['message'].lower()


class TestSecurityScenarios:
    """Test security-critical scenarios."""
    
    @pytest.mark.asyncio
    async def test_payload_with_injected_user_id(
        self,
        lambda_context,
        tenant_context
    ):
        """Test that injected user_id in payload is detected."""
        payload = {
            "instance": "test-instance",
            "event": "messages.upsert",
            "user_id": "injected-user-123",  # Malicious injection
            "data": {
                "key": {
                    "remoteJid": "5511999999999@s.whatsapp.net",
                    "fromMe": False,
                    "id": "123"
                },
                "message": {"conversation": "Test"}
            }
        }
        event = {"body": json.dumps(payload)}
        
        handler = MessageIngestionHandler()
        
        # Should log but not necessarily block (depends on implementation)
        with patch.object(
            handler.middleware,
            'validate_and_resolve',
            new_callable=AsyncMock
        ) as mock_validate:
            # Cross-tenant detection should catch this
            mock_validate.return_value = (
                None,
                {'cross_tenant': 'Suspicious payload detected'}
            )
            
            response = await handler.process_webhook(event, lambda_context)
        
        assert response['statusCode'] == 403
    
    @pytest.mark.asyncio
    async def test_payload_with_injected_tenant_id(
        self,
        lambda_context
    ):
        """Test that injected tenant_id in payload is rejected."""
        payload = {
            "instance": "test-instance",
            "event": "messages.upsert",
            "tenant_id": "malicious-tenant",  # Malicious injection
            "data": {
                "key": {
                    "remoteJid": "5511999999999@s.whatsapp.net",
                    "fromMe": False,
                    "id": "123"
                },
                "message": {"conversation": "Test"}
            }
        }
        event = {"body": json.dumps(payload)}
        
        handler = MessageIngestionHandler()
        
        with patch.object(
            handler.middleware,
            'validate_and_resolve',
            new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.return_value = (
                None,
                {'cross_tenant': 'Cross-tenant access attempt detected'}
            )
            
            response = await handler.process_webhook(event, lambda_context)
        
        assert response['statusCode'] == 403
        body = json.loads(response['body'])
        assert 'Cross-tenant' in body['error']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
