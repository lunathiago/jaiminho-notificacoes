"""SendPulse WhatsApp API adapter for outbound notifications.

This module provides a comprehensive adapter for the SendPulse WhatsApp API.

Responsibilities:
- Send urgent notifications immediately
- Send daily digests
- Send interactive feedback buttons
- Resolve destination phone number using user_id
- Outbound-only (never receives messages)

SendPulse API Reference:
https://sendpulse.com/api/whatsapp
"""

import json
import os
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import asyncio
import aiohttp
import boto3
from abc import ABC, abstractmethod

from jaiminho_notificacoes.core.logger import TenantContextLogger
from jaiminho_notificacoes.core.tenant import TenantIsolationMiddleware


logger = TenantContextLogger(__name__)

# Environment variables
SENDPULSE_SECRET_ARN = os.getenv('SENDPULSE_SECRET_ARN')
DYNAMODB_USER_PROFILES_TABLE = os.getenv('DYNAMODB_USER_PROFILES_TABLE', 'jaiminho-user-profiles')

# Lazy-loaded AWS clients (to avoid initialization errors when not in AWS)
_secrets_manager = None
_dynamodb = None
_cloudwatch = None


def get_secrets_manager():
    """Get or create SecretsManager client."""
    global _secrets_manager
    if _secrets_manager is None:
        _secrets_manager = boto3.client('secretsmanager')
    return _secrets_manager


def get_dynamodb():
    """Get or create DynamoDB resource."""
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource('dynamodb')
    return _dynamodb


def get_cloudwatch():
    """Get or create CloudWatch client."""
    global _cloudwatch
    if _cloudwatch is None:
        _cloudwatch = boto3.client('cloudwatch')
    return _cloudwatch


class NotificationType(str, Enum):
    """Types of notifications SendPulse can send."""
    URGENT = "urgent"  # Immediate notification
    DIGEST = "digest"  # Daily digest
    FEEDBACK = "feedback"  # Feedback buttons
    TRANSACTIONAL = "transactional"  # System message


class SendPulseTemplate(str, Enum):
    """Pre-defined SendPulse message templates."""
    URGENT_ALERT = "urgent_alert"
    DAILY_DIGEST = "daily_digest"
    FEEDBACK_BUTTONS = "feedback_buttons"
    WELCOME = "welcome"
    CONFIRM = "confirm"


@dataclass
class SendPulseButton:
    """Interactive button in SendPulse message."""
    id: str  # Unique button ID
    title: str  # Button label (max 20 chars)
    action: str  # Button action type


@dataclass
class SendPulseContent:
    """Content for SendPulse message."""
    text: str = ""  # Message text (required)
    media_url: Optional[str] = None  # Optional media
    caption: Optional[str] = None  # Media caption
    buttons: List[SendPulseButton] = field(default_factory=list)

    def validate(self) -> tuple[bool, str]:
        """Validate content."""
        if not self.text or len(self.text.strip()) == 0:
            return False, "Text content is required"

        if len(self.text) > 4096:
            return False, "Text exceeds 4096 character limit"

        if len(self.buttons) > 3:
            return False, "Maximum 3 buttons allowed"

        for button in self.buttons:
            if len(button.title) > 20:
                return False, f"Button title '{button.title}' exceeds 20 chars"

        return True, ""


@dataclass
class SendPulseMessage:
    """Message to send via SendPulse."""
    recipient_phone: str  # Phone number (with country code)
    content: SendPulseContent
    message_type: NotificationType
    tenant_id: str
    user_id: str
    message_id: Optional[str] = None  # For tracking
    template_name: Optional[SendPulseTemplate] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def validate(self) -> tuple[bool, str]:
        """Validate message."""
        # Validate tenant/user
        if not self.tenant_id or not self.user_id:
            return False, "tenant_id and user_id required"

        # Validate phone
        if not self._validate_phone(self.recipient_phone):
            return False, f"Invalid phone number: {self.recipient_phone}"

        # Validate content
        return self.content.validate()

    @staticmethod
    def _validate_phone(phone: str) -> bool:
        """Validate WhatsApp phone format."""
        # Remove non-digits
        digits_only = re.sub(r'\D', '', phone)
        # Must be 10-15 digits
        return 10 <= len(digits_only) <= 15

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API."""
        return {
            'recipient_phone': self.recipient_phone,
            'content': asdict(self.content),
            'message_type': self.message_type.value,
            'tenant_id': self.tenant_id,
            'user_id': self.user_id,
            'message_id': self.message_id,
            'template_name': self.template_name.value if self.template_name else None,
            'metadata': self.metadata,
            'created_at': self.created_at,
        }


@dataclass
class SendPulseResponse:
    """Response from SendPulse API."""
    success: bool
    message_id: Optional[str] = None
    status: Optional[str] = None
    error: Optional[str] = None
    api_response: Optional[Dict[str, Any]] = None
    sent_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


class SendPulseAuthenticator:
    """Handles SendPulse API authentication."""

    def __init__(self):
        """Initialize authenticator."""
        self.credentials = None
        self.token = None
        self.token_expires_at = None

    async def get_credentials(self) -> Dict[str, str]:
        """Get SendPulse credentials from Secrets Manager."""
        if self.credentials:
            return self.credentials

        try:
            if not SENDPULSE_SECRET_ARN:
                raise ValueError("SENDPULSE_SECRET_ARN not configured")

            response = get_secrets_manager().get_secret_value(SecretId=SENDPULSE_SECRET_ARN)
            self.credentials = json.loads(response['SecretString'])
            return self.credentials

        except Exception as e:
            logger.error(f"Failed to retrieve SendPulse credentials: {e}")
            raise

    async def get_token(self) -> str:
        """Get or refresh OAuth token from SendPulse."""
        # Check if token is still valid
        if self.token and self.token_expires_at:
            if datetime.utcnow().timestamp() < self.token_expires_at:
                return self.token

        credentials = await self.get_credentials()

        try:
            async with aiohttp.ClientSession() as session:
                # Authenticate
                auth_url = f"{credentials.get('api_url', 'https://api.sendpulse.com')}/oauth/access_token"
                auth_data = {
                    'grant_type': 'client_credentials',
                    'client_id': credentials['client_id'],
                    'client_secret': credentials['client_secret'],
                }

                async with session.post(auth_url, json=auth_data) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise ValueError(f"Auth failed: {error_text}")

                    data = await response.json()
                    self.token = data['access_token']
                    self.token_expires_at = datetime.utcnow().timestamp() + data.get('expires_in', 3600)
                    return self.token

        except Exception as e:
            logger.error(f"Failed to get SendPulse token: {e}")
            raise


class SendPulseUserResolver:
    """Resolves user phone numbers from user_id."""

    def __init__(self):
        """Initialize resolver."""
        self.user_cache = {}

    async def resolve_phone(
        self,
        tenant_id: str,
        user_id: str
    ) -> Optional[str]:
        """
        Resolve phone number for a user.

        Looks up user profile in DynamoDB.

        Args:
            tenant_id: Tenant ID
            user_id: User ID

        Returns:
            Phone number with country code, or None if not found
        """
        try:
            # Check cache first
            cache_key = f"{tenant_id}#{user_id}"
            if cache_key in self.user_cache:
                return self.user_cache[cache_key]['phone']

            # Query DynamoDB
            table = get_dynamodb().Table(DYNAMODB_USER_PROFILES_TABLE)

            response = table.get_item(
                Key={
                    'tenant_id': tenant_id,
                    'user_id': user_id
                }
            )

            item = response.get('Item')
            if not item:
                logger.warning(
                    "User not found",
                    tenant_id=tenant_id,
                    user_id=user_id
                )
                return None

            phone = item.get('whatsapp_phone')
            if not phone:
                logger.warning(
                    "User has no WhatsApp phone",
                    tenant_id=tenant_id,
                    user_id=user_id
                )
                return None

            # Cache result
            self.user_cache[cache_key] = {
                'phone': phone,
                'cached_at': datetime.utcnow().isoformat()
            }

            return phone

        except Exception as e:
            logger.error(f"Error resolving user phone: {e}")
            return None

    async def resolve_phones_batch(
        self,
        tenant_id: str,
        user_ids: List[str]
    ) -> Dict[str, Optional[str]]:
        """Resolve multiple phone numbers efficiently."""
        results = {}
        for user_id in user_ids:
            phone = await self.resolve_phone(tenant_id, user_id)
            results[user_id] = phone
        return results


class SendPulseClient(ABC):
    """Abstract base client for SendPulse API."""

    def __init__(self):
        """Initialize client."""
        self.authenticator = SendPulseAuthenticator()
        self.resolver = SendPulseUserResolver()
        self.middleware = TenantIsolationMiddleware()

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        timeout: int = 30
    ) -> Dict[str, Any]:
        """Make HTTP request to SendPulse API."""
        try:
            credentials = await self.authenticator.get_credentials()
            token = await self.authenticator.get_token()

            url = f"{credentials.get('api_url', 'https://api.sendpulse.com')}/{endpoint}"

            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }

            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method,
                    url,
                    json=data,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as response:
                    response_data = await response.json()

                    if response.status not in [200, 201, 202]:
                        logger.warning(
                            f"SendPulse API error: {response.status}",
                            endpoint=endpoint,
                            response=response_data
                        )

                    return {
                        'status': response.status,
                        'data': response_data
                    }

        except asyncio.TimeoutError:
            logger.error(f"SendPulse API timeout: {endpoint}")
            raise

        except Exception as e:
            logger.error(f"SendPulse API request failed: {e}")
            raise

    @abstractmethod
    async def send(self, message: SendPulseMessage) -> SendPulseResponse:
        """Send message via SendPulse."""
        pass


class SendPulseUrgentNotifier(SendPulseClient):
    """Sends urgent notifications via SendPulse."""

    async def send(self, message: SendPulseMessage) -> SendPulseResponse:
        """
        Send urgent notification immediately.

        Args:
            message: Message to send

        Returns:
            SendPulseResponse with status
        """
        try:
            # Validate message
            valid, error = message.validate()
            if not valid:
                logger.warning(f"Invalid message: {error}")
                return SendPulseResponse(success=False, error=error)

            # Validate tenant context
            tenant_context = {
                'tenant_id': message.tenant_id,
                'user_id': message.user_id
            }
            self.middleware.validate_tenant_context(tenant_context)

            logger.info(
                "Sending urgent notification",
                tenant_id=message.tenant_id,
                user_id=message.user_id,
                recipient_phone=message.recipient_phone
            )

            # Build SendPulse API request
            payload = {
                'recipient': message.recipient_phone,
                'content': {
                    'type': 'text',
                    'text': message.content.text,
                },
                'priority': 'HIGH',
                'metadata': {
                    'message_id': message.message_id,
                    'user_id': message.user_id,
                    'tenant_id': message.tenant_id,
                    'notification_type': 'urgent',
                    'timestamp': message.created_at,
                }
            }

            # Add media if present
            if message.content.media_url:
                payload['content'] = {
                    'type': 'media',
                    'media_url': message.content.media_url,
                    'caption': message.content.caption or ''
                }

            # Add buttons if present
            if message.content.buttons:
                payload['interactive'] = {
                    'type': 'button',
                    'body': {'text': message.content.text},
                    'action': {
                        'buttons': [
                            {
                                'type': 'reply',
                                'reply': {
                                    'id': btn.id,
                                    'title': btn.title
                                }
                            }
                            for btn in message.content.buttons
                        ]
                    }
                }

            # Send via SendPulse
            response = await self._make_request('POST', 'v1/whatsapp/send', payload)

            if response['status'] in [200, 201, 202]:
                api_data = response['data']
                sendpulse_message_id = api_data.get('id') or api_data.get('message_id')

                logger.info(
                    "Urgent notification sent",
                    sendpulse_message_id=sendpulse_message_id,
                    user_id=message.user_id
                )

                # Emit CloudWatch metric
                await self._emit_metric('UrgentNotificationSent')

                return SendPulseResponse(
                    success=True,
                    message_id=sendpulse_message_id,
                    status='sent',
                    api_response=api_data
                )
            else:
                error = response['data'].get('error', 'Unknown error')
                return SendPulseResponse(
                    success=False,
                    error=error,
                    api_response=response['data']
                )

        except Exception as e:
            logger.error(f"Failed to send urgent notification: {e}")
            return SendPulseResponse(
                success=False,
                error=f"Exception: {str(e)}"
            )

    async def _emit_metric(self, metric_name: str):
        """Emit CloudWatch metric."""
        try:
            get_cloudwatch().put_metric_data(
                Namespace='JaininhoNotificacoes/SendPulse',
                MetricData=[{
                    'MetricName': metric_name,
                    'Value': 1,
                    'Unit': 'Count'
                }]
            )
        except Exception as e:
            logger.warning(f"Failed to emit metric: {e}")


class SendPulseDigestSender(SendPulseClient):
    """Sends daily digests via SendPulse."""

    async def send(self, message: SendPulseMessage) -> SendPulseResponse:
        """
        Send daily digest.

        Args:
            message: Digest message to send

        Returns:
            SendPulseResponse with status
        """
        try:
            # Validate
            valid, error = message.validate()
            if not valid:
                return SendPulseResponse(success=False, error=error)

            # Validate tenant context
            tenant_context = {
                'tenant_id': message.tenant_id,
                'user_id': message.user_id
            }
            self.middleware.validate_tenant_context(tenant_context)

            logger.info(
                "Sending daily digest",
                tenant_id=message.tenant_id,
                user_id=message.user_id
            )

            # Build payload
            payload = {
                'recipient': message.recipient_phone,
                'content': {
                    'type': 'text',
                    'text': message.content.text,
                },
                'priority': 'MEDIUM',
                'schedule_time': message.metadata.get('schedule_time'),
                'metadata': {
                    'message_id': message.message_id,
                    'user_id': message.user_id,
                    'tenant_id': message.tenant_id,
                    'notification_type': 'digest',
                    'timestamp': message.created_at,
                }
            }

            # Send
            response = await self._make_request('POST', 'v1/whatsapp/send', payload)

            if response['status'] in [200, 201, 202]:
                api_data = response['data']
                sendpulse_message_id = api_data.get('id') or api_data.get('message_id')

                logger.info(
                    "Daily digest sent",
                    sendpulse_message_id=sendpulse_message_id,
                    user_id=message.user_id
                )

                return SendPulseResponse(
                    success=True,
                    message_id=sendpulse_message_id,
                    status='queued',
                    api_response=api_data
                )
            else:
                error = response['data'].get('error', 'Unknown error')
                return SendPulseResponse(
                    success=False,
                    error=error,
                    api_response=response['data']
                )

        except Exception as e:
            logger.error(f"Failed to send digest: {e}")
            return SendPulseResponse(
                success=False,
                error=f"Exception: {str(e)}"
            )


class SendPulseFeedbackSender(SendPulseClient):
    """Sends interactive feedback buttons via SendPulse."""

    async def send(self, message: SendPulseMessage) -> SendPulseResponse:
        """
        Send message with feedback buttons.

        Args:
            message: Message with buttons to send

        Returns:
            SendPulseResponse with status
        """
        try:
            # Validate
            valid, error = message.validate()
            if not valid:
                return SendPulseResponse(success=False, error=error)

            if not message.content.buttons:
                return SendPulseResponse(
                    success=False,
                    error="Feedback message requires buttons"
                )

            # Validate tenant
            tenant_context = {
                'tenant_id': message.tenant_id,
                'user_id': message.user_id
            }
            self.middleware.validate_tenant_context(tenant_context)

            logger.info(
                "Sending feedback message",
                tenant_id=message.tenant_id,
                user_id=message.user_id,
                button_count=len(message.content.buttons)
            )

            # Build interactive payload
            payload = {
                'recipient': message.recipient_phone,
                'interactive': {
                    'type': 'button',
                    'body': {
                        'text': message.content.text
                    },
                    'action': {
                        'buttons': [
                            {
                                'type': 'reply',
                                'reply': {
                                    'id': btn.id,
                                    'title': btn.title
                                }
                            }
                            for btn in message.content.buttons
                        ]
                    }
                },
                'metadata': {
                    'message_id': message.message_id,
                    'user_id': message.user_id,
                    'tenant_id': message.tenant_id,
                    'notification_type': 'feedback',
                    'timestamp': message.created_at,
                }
            }

            # Send
            response = await self._make_request('POST', 'v1/whatsapp/send', payload)

            if response['status'] in [200, 201, 202]:
                api_data = response['data']
                sendpulse_message_id = api_data.get('id') or api_data.get('message_id')

                logger.info(
                    "Feedback message sent",
                    sendpulse_message_id=sendpulse_message_id,
                    user_id=message.user_id,
                    button_count=len(message.content.buttons)
                )

                return SendPulseResponse(
                    success=True,
                    message_id=sendpulse_message_id,
                    status='sent',
                    api_response=api_data
                )
            else:
                error = response['data'].get('error', 'Unknown error')
                return SendPulseResponse(
                    success=False,
                    error=error,
                    api_response=response['data']
                )

        except Exception as e:
            logger.error(f"Failed to send feedback message: {e}")
            return SendPulseResponse(
                success=False,
                error=f"Exception: {str(e)}"
            )


class SendPulseNotificationFactory:
    """Factory for creating appropriate SendPulse sender."""

    @staticmethod
    def get_sender(message_type: NotificationType) -> SendPulseClient:
        """
        Get appropriate sender based on message type.

        Args:
            message_type: Type of notification to send

        Returns:
            SendPulseClient instance
        """
        if message_type == NotificationType.URGENT:
            return SendPulseUrgentNotifier()
        elif message_type == NotificationType.DIGEST:
            return SendPulseDigestSender()
        elif message_type == NotificationType.FEEDBACK:
            return SendPulseFeedbackSender()
        else:
            return SendPulseUrgentNotifier()  # Default


class SendPulseManager:
    """
    High-level manager for SendPulse operations.

    Coordinates notification sending with user resolution.
    """

    def __init__(self):
        """Initialize manager."""
        self.resolver = SendPulseUserResolver()
        self.middleware = TenantIsolationMiddleware()

    async def send_notification(
        self,
        tenant_id: str,
        user_id: str,
        content_text: str,
        message_type: NotificationType = NotificationType.URGENT,
        recipient_phone: Optional[str] = None,
        buttons: Optional[List[SendPulseButton]] = None,
        media_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> SendPulseResponse:
        """
        Send notification via SendPulse.

        Args:
            tenant_id: Tenant ID
            user_id: User ID
            content_text: Message text
            message_type: Type of notification
            recipient_phone: Override phone (optional)
            buttons: Interactive buttons (optional)
            media_url: Media URL (optional)
            metadata: Additional metadata (optional)

        Returns:
            SendPulseResponse
        """
        try:
            # Validate tenant context
            self.middleware.validate_tenant_context({
                'tenant_id': tenant_id,
                'user_id': user_id
            })

            # Resolve phone if not provided
            if not recipient_phone:
                recipient_phone = await self.resolver.resolve_phone(tenant_id, user_id)

            if not recipient_phone:
                logger.error(
                    "Failed to resolve recipient phone",
                    tenant_id=tenant_id,
                    user_id=user_id
                )
                return SendPulseResponse(
                    success=False,
                    error="Could not resolve recipient phone number"
                )

            # Create message
            content = SendPulseContent(
                text=content_text,
                media_url=media_url,
                buttons=buttons or []
            )

            message = SendPulseMessage(
                recipient_phone=recipient_phone,
                content=content,
                message_type=message_type,
                tenant_id=tenant_id,
                user_id=user_id,
                metadata=metadata or {}
            )

            # Get appropriate sender
            sender = SendPulseNotificationFactory.get_sender(message_type)

            # Send
            result = await sender.send(message)

            return result

        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            return SendPulseResponse(
                success=False,
                error=f"Exception: {str(e)}"
            )

    async def send_batch(
        self,
        tenant_id: str,
        user_ids: List[str],
        content_text: str,
        message_type: NotificationType = NotificationType.DIGEST
    ) -> List[SendPulseResponse]:
        """
        Send notification to multiple users.

        Args:
            tenant_id: Tenant ID
            user_ids: List of user IDs
            content_text: Message text
            message_type: Type of notification

        Returns:
            List of SendPulseResponse
        """
        try:
            logger.info(
                "Sending batch notifications",
                tenant_id=tenant_id,
                user_count=len(user_ids)
            )

            results = []
            for user_id in user_ids:
                result = await self.send_notification(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    content_text=content_text,
                    message_type=message_type
                )
                results.append(result)

            return results

        except Exception as e:
            logger.error(f"Batch notification failed: {e}")
            return []
