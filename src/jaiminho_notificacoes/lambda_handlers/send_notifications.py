"""Lambda handler: Outbound notification delivery via SendPulse.

Handles:
1. Urgent notifications (immediate)
2. Daily digests (batch)
3. Feedback buttons (interactive)

Event structure:
{
    'tenant_id': str,
    'user_id': str,
    'notification_type': 'urgent' | 'digest' | 'feedback',
    'content_text': str,
    'recipient_phone': str (optional),
    'buttons': [{id, title, action}] (optional),
    'media_url': str (optional),
    'metadata': dict (optional),
    'wapi_instance_id': str (obrigatorio para feedback)
}
"""

import json
import asyncio
from typing import Any, Dict, List, Optional

from jaiminho_notificacoes.outbound.sendpulse import (
    SendPulseManager,
    SendPulseButton,
    NotificationType,
    SendPulseResponse
)
from jaiminho_notificacoes.core.logger import TenantContextLogger


logger = TenantContextLogger(__name__)

# Lazy-load middleware to avoid AWS initialization issues
_middleware = None


def get_middleware():
    """Get or create TenantIsolationMiddleware."""
    global _middleware
    if _middleware is None:
        from jaiminho_notificacoes.core.tenant import TenantIsolationMiddleware
        _middleware = TenantIsolationMiddleware()
    return _middleware


async def send_notification_async(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send a single notification via SendPulse.

    Args:
        event: Lambda event

    Returns:
        Response with result
    """
    try:
        # Extract and validate parameters
        tenant_id = event.get('tenant_id')
        user_id = event.get('user_id')
        notification_type_str = event.get('notification_type', 'urgent')
        content_text = event.get('content_text')

        if not all([tenant_id, user_id, content_text]):
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'success': False,
                    'error': 'Missing required parameters: tenant_id, user_id, content_text'
                })
            }

        # Map notification type
        try:
            notification_type = NotificationType(notification_type_str)
        except ValueError:
            notification_type = NotificationType.URGENT

        # Extract optional parameters
        recipient_phone = event.get('recipient_phone')
        media_url = event.get('media_url')
        metadata = event.get('metadata', {}) or {}
        wapi_instance_id = event.get('wapi_instance_id') or metadata.get('wapi_instance_id')

        if notification_type == NotificationType.FEEDBACK and not wapi_instance_id:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'success': False,
                    'error': 'wapi_instance_id required for feedback notifications'
                })
            }

        metadata = metadata.copy()
        metadata.pop('wapi_instance_id', None)

        # Build buttons if provided
        buttons = None
        if 'buttons' in event:
            buttons = [
                SendPulseButton(
                    id=btn.get('id', f'btn_{i}'),
                    title=btn.get('title', ''),
                    action=btn.get('action', 'reply')
                )
                for i, btn in enumerate(event.get('buttons', []))
            ]

        logger.info(
            "Processing notification",
            tenant_id=tenant_id,
            user_id=user_id,
            notification_type=notification_type.value
        )

        # Send via SendPulse
        manager = SendPulseManager()
        result = await manager.send_notification(
            tenant_id=tenant_id,
            user_id=user_id,
            content_text=content_text,
            message_type=notification_type,
            recipient_phone=recipient_phone,
            buttons=buttons,
            media_url=media_url,
            metadata=metadata,
            wapi_instance_id=wapi_instance_id
        )

        response_body = {
            'success': result.success,
            'message_id': result.message_id,
            'status': result.status,
            'error': result.error,
            'sent_at': result.sent_at
        }

        status_code = 200 if result.success else 400

        logger.info(
            "Notification processed",
            status_code=status_code,
            success=result.success,
            message_id=result.message_id
        )

        return {
            'statusCode': status_code,
            'body': json.dumps(response_body)
        }

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'success': False,
                'error': f"Internal error: {str(e)}"
            })
        }


async def send_batch_notifications_async(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send notifications to multiple users.

    Event structure:
    {
        'tenant_id': str,
        'user_ids': [str],
        'notification_type': 'digest' | 'urgent',
        'content_text': str,
        'metadata': dict (optional)
    }

    Args:
        event: Lambda event

    Returns:
        Response with batch results
    """
    try:
        # Extract parameters
        tenant_id = event.get('tenant_id')
        user_ids = event.get('user_ids', [])
        notification_type_str = event.get('notification_type', 'digest')
        content_text = event.get('content_text')

        if not all([tenant_id, user_ids, content_text]):
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'success': False,
                    'error': 'Missing required parameters'
                })
            }

        try:
            notification_type = NotificationType(notification_type_str)
        except ValueError:
            notification_type = NotificationType.DIGEST

        logger.info(
            "Processing batch notifications",
            tenant_id=tenant_id,
            user_count=len(user_ids),
            notification_type=notification_type.value
        )

        # Send batch
        manager = SendPulseManager()
        results = await manager.send_batch(
            tenant_id=tenant_id,
            user_ids=user_ids,
            content_text=content_text,
            message_type=notification_type
        )

        # Summarize results
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful

        response_body = {
            'success': failed == 0,
            'total': len(results),
            'successful': successful,
            'failed': failed,
            'results': [r.to_dict() for r in results]
        }

        status_code = 200 if response_body['success'] else 207  # Multi-status

        logger.info(
            "Batch notifications processed",
            status_code=status_code,
            successful=successful,
            failed=failed
        )

        return {
            'statusCode': status_code,
            'body': json.dumps(response_body)
        }

    except Exception as e:
        logger.error(f"Batch error: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'success': False,
                'error': f"Internal error: {str(e)}"
            })
        }


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for sending notifications.

    Routes to single or batch handler based on event structure.

    Args:
        event: Lambda event
        context: Lambda context

    Returns:
        Lambda response
    """
    try:
        # Route based on event structure
        if 'user_ids' in event:
            # Batch notification
            return asyncio.run(send_batch_notifications_async(event))
        else:
            # Single notification
            return asyncio.run(send_notification_async(event))

    except Exception as e:
        logger.error(f"Handler error: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'success': False,
                'error': str(e)
            })
        }
