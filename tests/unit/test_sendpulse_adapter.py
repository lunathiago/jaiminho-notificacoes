"""Unit tests for SendPulse adapter."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json
from datetime import datetime

from jaiminho_notificacoes.outbound.sendpulse import (
    SendPulseButton,
    SendPulseContent,
    SendPulseMessage,
    SendPulseResponse,
    SendPulseAuthenticator,
    SendPulseUserResolver,
    SendPulseUrgentNotifier,
    SendPulseDigestSender,
    SendPulseFeedbackSender,
    SendPulseManager,
    NotificationType,
    SendPulseNotificationFactory
)


class TestSendPulseButton:
    """Tests for SendPulseButton."""

    def test_button_creation(self):
        """Test button creation."""
        button = SendPulseButton(
            id='btn_1',
            title='Yes',
            action='reply'
        )
        assert button.id == 'btn_1'
        assert button.title == 'Yes'
        assert button.action == 'reply'


class TestSendPulseContent:
    """Tests for SendPulseContent."""

    def test_valid_content(self):
        """Test valid content validation."""
        content = SendPulseContent(text='Hello')
        valid, error = content.validate()
        assert valid is True
        assert error == ""

    def test_empty_content(self):
        """Test empty content validation."""
        content = SendPulseContent(text='')
        valid, error = content.validate()
        assert valid is False
        assert "required" in error.lower()

    def test_text_too_long(self):
        """Test text length validation."""
        content = SendPulseContent(text='x' * 5000)
        valid, error = content.validate()
        assert valid is False
        assert "exceeds" in error.lower()

    def test_too_many_buttons(self):
        """Test button count validation."""
        buttons = [
            SendPulseButton(id=f'btn_{i}', title=f'Option {i}', action='reply')
            for i in range(4)
        ]
        content = SendPulseContent(text='Choose', buttons=buttons)
        valid, error = content.validate()
        assert valid is False
        assert "maximum" in error.lower()

    def test_button_title_too_long(self):
        """Test button title length validation."""
        button = SendPulseButton(id='btn_1', title='x' * 25, action='reply')
        content = SendPulseContent(text='Choose', buttons=[button])
        valid, error = content.validate()
        assert valid is False
        assert "exceeds 20" in error

    def test_content_with_buttons(self):
        """Test valid content with buttons."""
        buttons = [
            SendPulseButton(id='yes', title='Yes', action='reply'),
            SendPulseButton(id='no', title='No', action='reply')
        ]
        content = SendPulseContent(text='Confirm?', buttons=buttons)
        valid, error = content.validate()
        assert valid is True


class TestSendPulseMessage:
    """Tests for SendPulseMessage."""

    def test_valid_message(self):
        """Test valid message validation."""
        content = SendPulseContent(text='Hello')
        message = SendPulseMessage(
            recipient_phone='554899999999',
            content=content,
            message_type=NotificationType.URGENT,
            tenant_id='tenant_1',
            user_id='user_1'
        )
        valid, error = message.validate()
        assert valid is True

    def test_invalid_phone(self):
        """Test invalid phone validation."""
        content = SendPulseContent(text='Hello')
        message = SendPulseMessage(
            recipient_phone='123',  # Too short
            content=content,
            message_type=NotificationType.URGENT,
            tenant_id='tenant_1',
            user_id='user_1'
        )
        valid, error = message.validate()
        assert valid is False
        assert "Invalid phone" in error

    def test_missing_tenant(self):
        """Test missing tenant validation."""
        content = SendPulseContent(text='Hello')
        message = SendPulseMessage(
            recipient_phone='554899999999',
            content=content,
            message_type=NotificationType.URGENT,
            tenant_id='',
            user_id='user_1'
        )
        valid, error = message.validate()
        assert valid is False
        assert "required" in error.lower()

    def test_phone_formats(self):
        """Test various phone formats."""
        test_phones = [
            ('554899999999', True),  # Brazil format
            ('+55 48 9 9999-9999', True),  # With formatting
            ('48999999999', True),  # Without country code
            ('123', False),  # Too short
            ('1234567890123456', False),  # Too long
        ]

        content = SendPulseContent(text='Test')
        for phone, expected_valid in test_phones:
            is_valid = SendPulseMessage._validate_phone(phone)
            assert is_valid == expected_valid, f"Phone {phone} validation failed"

    def test_message_to_dict(self):
        """Test message conversion to dict."""
        content = SendPulseContent(text='Hello')
        message = SendPulseMessage(
            recipient_phone='554899999999',
            content=content,
            message_type=NotificationType.URGENT,
            tenant_id='tenant_1',
            user_id='user_1',
            message_id='msg_123'
        )
        result = message.to_dict()
        assert result['recipient_phone'] == '554899999999'
        assert result['message_type'] == 'urgent'
        assert result['tenant_id'] == 'tenant_1'
        assert result['message_id'] == 'msg_123'


class TestSendPulseResponse:
    """Tests for SendPulseResponse."""

    def test_success_response(self):
        """Test successful response."""
        response = SendPulseResponse(
            success=True,
            message_id='sendpulse_123',
            status='sent'
        )
        assert response.success is True
        assert response.message_id == 'sendpulse_123'

    def test_error_response(self):
        """Test error response."""
        response = SendPulseResponse(
            success=False,
            error='Failed to send'
        )
        assert response.success is False
        assert response.error == 'Failed to send'

    def test_response_to_dict(self):
        """Test response conversion to dict."""
        response = SendPulseResponse(
            success=True,
            message_id='msg_123',
            status='sent'
        )
        result = response.to_dict()
        assert result['success'] is True
        assert result['message_id'] == 'msg_123'
        assert 'sent_at' in result


class TestSendPulseAuthenticator:
    """Tests for SendPulseAuthenticator."""

    @pytest.mark.asyncio
    async def test_get_credentials(self):
        """Test getting credentials from Secrets Manager."""
        with patch('jaiminho_notificacoes.outbound.sendpulse.secrets_manager') as mock_sm:
            mock_sm.get_secret_value.return_value = {
                'SecretString': json.dumps({
                    'client_id': 'test_client',
                    'client_secret': 'test_secret',
                    'api_url': 'https://api.sendpulse.com'
                })
            }

            auth = SendPulseAuthenticator()
            creds = await auth.get_credentials()

            assert creds['client_id'] == 'test_client'
            assert creds['client_secret'] == 'test_secret'

    @pytest.mark.asyncio
    async def test_token_caching(self):
        """Test token caching."""
        with patch('jaiminho_notificacoes.outbound.sendpulse.secrets_manager') as mock_sm:
            mock_sm.get_secret_value.return_value = {
                'SecretString': json.dumps({
                    'client_id': 'test_client',
                    'client_secret': 'test_secret'
                })
            }

            with patch('aiohttp.ClientSession') as mock_session:
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.json = AsyncMock(return_value={
                    'access_token': 'token_123',
                    'expires_in': 3600
                })
                mock_session.return_value.__aenter__.return_value.post = AsyncMock(
                    return_value=mock_response
                )

                auth = SendPulseAuthenticator()

                # First call
                token1 = await auth.get_token()
                assert token1 == 'token_123'

                # Second call should use cached token
                token2 = await auth.get_token()
                assert token2 == 'token_123'


class TestSendPulseUserResolver:
    """Tests for SendPulseUserResolver."""

    @pytest.mark.asyncio
    async def test_resolve_phone(self):
        """Test phone number resolution."""
        with patch('jaiminho_notificacoes.outbound.sendpulse.dynamodb') as mock_db:
            mock_table = MagicMock()
            mock_table.get_item.return_value = {
                'Item': {
                    'tenant_id': 'tenant_1',
                    'user_id': 'user_1',
                    'whatsapp_phone': '554899999999'
                }
            }
            mock_db.Table.return_value = mock_table

            resolver = SendPulseUserResolver()
            phone = await resolver.resolve_phone('tenant_1', 'user_1')

            assert phone == '554899999999'

    @pytest.mark.asyncio
    async def test_resolve_phone_not_found(self):
        """Test phone resolution when user not found."""
        with patch('jaiminho_notificacoes.outbound.sendpulse.dynamodb') as mock_db:
            mock_table = MagicMock()
            mock_table.get_item.return_value = {'Item': None}
            mock_db.Table.return_value = mock_table

            resolver = SendPulseUserResolver()
            phone = await resolver.resolve_phone('tenant_1', 'user_1')

            assert phone is None

    @pytest.mark.asyncio
    async def test_phone_caching(self):
        """Test phone caching."""
        with patch('jaiminho_notificacoes.outbound.sendpulse.dynamodb') as mock_db:
            mock_table = MagicMock()
            mock_table.get_item.return_value = {
                'Item': {
                    'whatsapp_phone': '554899999999'
                }
            }
            mock_db.Table.return_value = mock_table

            resolver = SendPulseUserResolver()

            # First call
            phone1 = await resolver.resolve_phone('tenant_1', 'user_1')
            # Second call should use cache (get_item called only once)
            phone2 = await resolver.resolve_phone('tenant_1', 'user_1')

            assert phone1 == phone2
            assert mock_table.get_item.call_count == 1


class TestSendPulseUrgentNotifier:
    """Tests for SendPulseUrgentNotifier."""

    @pytest.mark.asyncio
    async def test_send_urgent_notification(self):
        """Test sending urgent notification."""
        with patch('jaiminho_notificacoes.outbound.sendpulse.cloudwatch') as mock_cw:
            notifier = SendPulseUrgentNotifier()
            notifier._make_request = AsyncMock(return_value={
                'status': 200,
                'data': {'id': 'sendpulse_123'}
            })

            content = SendPulseContent(text='Urgent alert')
            message = SendPulseMessage(
                recipient_phone='554899999999',
                content=content,
                message_type=NotificationType.URGENT,
                tenant_id='tenant_1',
                user_id='user_1'
            )

            response = await notifier.send(message)

            assert response.success is True
            assert response.message_id == 'sendpulse_123'

    @pytest.mark.asyncio
    async def test_send_urgent_with_buttons(self):
        """Test sending urgent notification with buttons."""
        notifier = SendPulseUrgentNotifier()
        notifier._make_request = AsyncMock(return_value={
            'status': 200,
            'data': {'id': 'sendpulse_123'}
        })

        buttons = [
            SendPulseButton(id='yes', title='Yes', action='reply'),
            SendPulseButton(id='no', title='No', action='reply')
        ]
        content = SendPulseContent(text='Confirm?', buttons=buttons)
        message = SendPulseMessage(
            recipient_phone='554899999999',
            content=content,
            message_type=NotificationType.URGENT,
            tenant_id='tenant_1',
            user_id='user_1'
        )

        response = await notifier.send(message)

        # Verify request payload contained buttons
        call_args = notifier._make_request.call_args
        payload = call_args[0][2]  # Third arg is data
        assert 'interactive' in payload


class TestSendPulseDigestSender:
    """Tests for SendPulseDigestSender."""

    @pytest.mark.asyncio
    async def test_send_digest(self):
        """Test sending digest."""
        sender = SendPulseDigestSender()
        sender._make_request = AsyncMock(return_value={
            'status': 200,
            'data': {'id': 'sendpulse_456'}
        })

        content = SendPulseContent(text='Daily digest')
        message = SendPulseMessage(
            recipient_phone='554899999999',
            content=content,
            message_type=NotificationType.DIGEST,
            tenant_id='tenant_1',
            user_id='user_1'
        )

        response = await sender.send(message)

        assert response.success is True
        assert response.status == 'queued'


class TestSendPulseFeedbackSender:
    """Tests for SendPulseFeedbackSender."""

    @pytest.mark.asyncio
    async def test_send_feedback(self):
        """Test sending feedback message."""
        sender = SendPulseFeedbackSender()
        sender._make_request = AsyncMock(return_value={
            'status': 200,
            'data': {'id': 'sendpulse_789'}
        })

        buttons = [
            SendPulseButton(id='imp', title='Important', action='reply'),
            SendPulseButton(id='not_imp', title='Not Important', action='reply')
        ]
        content = SendPulseContent(text='Is this important?', buttons=buttons)
        message = SendPulseMessage(
            recipient_phone='554899999999',
            content=content,
            message_type=NotificationType.FEEDBACK,
            tenant_id='tenant_1',
            user_id='user_1'
        )

        response = await sender.send(message)

        assert response.success is True

    @pytest.mark.asyncio
    async def test_send_feedback_without_buttons(self):
        """Test sending feedback message without buttons."""
        sender = SendPulseFeedbackSender()

        content = SendPulseContent(text='No buttons')
        message = SendPulseMessage(
            recipient_phone='554899999999',
            content=content,
            message_type=NotificationType.FEEDBACK,
            tenant_id='tenant_1',
            user_id='user_1'
        )

        response = await sender.send(message)

        assert response.success is False
        assert "requires buttons" in response.error


class TestSendPulseNotificationFactory:
    """Tests for SendPulseNotificationFactory."""

    def test_get_urgent_notifier(self):
        """Test getting urgent notifier."""
        sender = SendPulseNotificationFactory.get_sender(NotificationType.URGENT)
        assert isinstance(sender, SendPulseUrgentNotifier)

    def test_get_digest_sender(self):
        """Test getting digest sender."""
        sender = SendPulseNotificationFactory.get_sender(NotificationType.DIGEST)
        assert isinstance(sender, SendPulseDigestSender)

    def test_get_feedback_sender(self):
        """Test getting feedback sender."""
        sender = SendPulseNotificationFactory.get_sender(NotificationType.FEEDBACK)
        assert isinstance(sender, SendPulseFeedbackSender)


class TestSendPulseManager:
    """Tests for SendPulseManager."""

    @pytest.mark.asyncio
    async def test_send_notification_with_phone(self):
        """Test sending notification with resolved phone."""
        manager = SendPulseManager()

        with patch.object(manager.resolver, 'resolve_phone', return_value='554899999999'):
            # Mock the sender
            with patch('jaiminho_notificacoes.outbound.sendpulse.SendPulseNotificationFactory.get_sender') as mock_factory:
                mock_sender = AsyncMock()
                mock_sender.send = AsyncMock(return_value=SendPulseResponse(
                    success=True,
                    message_id='msg_123'
                ))
                mock_factory.return_value = mock_sender

                response = await manager.send_notification(
                    tenant_id='tenant_1',
                    user_id='user_1',
                    content_text='Hello'
                )

                assert response.success is True

    @pytest.mark.asyncio
    async def test_send_notification_phone_not_found(self):
        """Test sending notification when phone not found."""
        manager = SendPulseManager()

        with patch.object(manager.resolver, 'resolve_phone', return_value=None):
            response = await manager.send_notification(
                tenant_id='tenant_1',
                user_id='user_1',
                content_text='Hello'
            )

            assert response.success is False
            assert "resolve" in response.error.lower()

    @pytest.mark.asyncio
    async def test_send_batch_notifications(self):
        """Test sending batch notifications."""
        manager = SendPulseManager()

        with patch.object(manager, 'send_notification') as mock_send:
            mock_send.return_value = SendPulseResponse(success=True)

            responses = await manager.send_batch(
                tenant_id='tenant_1',
                user_ids=['user_1', 'user_2'],
                content_text='Digest'
            )

            assert len(responses) == 2
            assert all(r.success for r in responses)
