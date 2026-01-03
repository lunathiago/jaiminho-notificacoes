"""Outbound notification module.

Provides adapters for sending notifications via various channels:
- SendPulse WhatsApp
"""

from jaiminho_notificacoes.outbound.sendpulse import (
    # Data models
    SendPulseButton,
    SendPulseContent,
    SendPulseMessage,
    SendPulseResponse,
    # Enums
    NotificationType,
    SendPulseTemplate,
    # Authenticator and resolver
    SendPulseAuthenticator,
    SendPulseUserResolver,
    # Clients
    SendPulseClient,
    SendPulseUrgentNotifier,
    SendPulseDigestSender,
    SendPulseFeedbackSender,
    # Manager and factory
    SendPulseManager,
    SendPulseNotificationFactory,
)

__all__ = [
    # Data models
    'SendPulseButton',
    'SendPulseContent',
    'SendPulseMessage',
    'SendPulseResponse',
    # Enums
    'NotificationType',
    'SendPulseTemplate',
    # Authenticator and resolver
    'SendPulseAuthenticator',
    'SendPulseUserResolver',
    # Clients
    'SendPulseClient',
    'SendPulseUrgentNotifier',
    'SendPulseDigestSender',
    'SendPulseFeedbackSender',
    # Manager and factory
    'SendPulseManager',
    'SendPulseNotificationFactory',
]
