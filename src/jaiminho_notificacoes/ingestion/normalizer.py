"""Message normalizer - convert Evolution API events to unified schema."""

from datetime import datetime
from typing import Dict, Optional
from pydantic import ValidationError

from ..core.logger import get_logger
from ..core.tenant import TenantContext
from ..persistence.models import (
    EvolutionWebhookEvent,
    MessageType,
    MessageContent,
    MessageMetadata,
    MessageSecurity,
    MessageSource as MessageSourceModel,
    NormalizedMessage
)

logger = get_logger(__name__)


class MessageNormalizer:
    """Normalize Evolution API messages to unified schema."""
    
    @staticmethod
    def _extract_message_text(message_data: Dict) -> Optional[str]:
        """Extract text from various message formats."""
        # Direct conversation
        if 'conversation' in message_data:
            return message_data['conversation']
        
        # Extended text message
        if 'extendedTextMessage' in message_data:
            ext_msg = message_data['extendedTextMessage']
            if isinstance(ext_msg, dict):
                return ext_msg.get('text')
        
        # Image caption
        if 'imageMessage' in message_data:
            img_msg = message_data['imageMessage']
            if isinstance(img_msg, dict):
                return img_msg.get('caption')
        
        # Video caption
        if 'videoMessage' in message_data:
            vid_msg = message_data['videoMessage']
            if isinstance(vid_msg, dict):
                return vid_msg.get('caption')
        
        # Document caption
        if 'documentMessage' in message_data:
            doc_msg = message_data['documentMessage']
            if isinstance(doc_msg, dict):
                return doc_msg.get('caption')
        
        return None
    
    @staticmethod
    def _detect_message_type(message_data: Dict) -> MessageType:
        """Detect message type from Evolution API format."""
        if 'conversation' in message_data or 'extendedTextMessage' in message_data:
            return MessageType.TEXT
        elif 'imageMessage' in message_data:
            return MessageType.IMAGE
        elif 'videoMessage' in message_data:
            return MessageType.VIDEO
        elif 'audioMessage' in message_data:
            return MessageType.AUDIO
        elif 'documentMessage' in message_data:
            return MessageType.DOCUMENT
        elif 'locationMessage' in message_data:
            return MessageType.LOCATION
        elif 'contactMessage' in message_data or 'contactsArrayMessage' in message_data:
            return MessageType.CONTACT
        else:
            return MessageType.UNKNOWN
    
    @staticmethod
    def _extract_media_info(message_data: Dict, message_type: MessageType) -> Dict:
        """Extract media information based on message type."""
        media_info = {}
        
        if message_type == MessageType.IMAGE and 'imageMessage' in message_data:
            img = message_data['imageMessage']
            if isinstance(img, dict):
                media_info['mime_type'] = img.get('mimetype')
                media_info['caption'] = img.get('caption')
                # URL would be generated/retrieved from Evolution API
                media_info['media_url'] = img.get('url')
        
        elif message_type == MessageType.VIDEO and 'videoMessage' in message_data:
            vid = message_data['videoMessage']
            if isinstance(vid, dict):
                media_info['mime_type'] = vid.get('mimetype')
                media_info['caption'] = vid.get('caption')
                media_info['media_url'] = vid.get('url')
        
        elif message_type == MessageType.DOCUMENT and 'documentMessage' in message_data:
            doc = message_data['documentMessage']
            if isinstance(doc, dict):
                media_info['mime_type'] = doc.get('mimetype')
                media_info['file_name'] = doc.get('fileName')
                media_info['caption'] = doc.get('caption')
                media_info['media_url'] = doc.get('url')
        
        elif message_type == MessageType.AUDIO and 'audioMessage' in message_data:
            audio = message_data['audioMessage']
            if isinstance(audio, dict):
                media_info['mime_type'] = audio.get('mimetype')
                media_info['media_url'] = audio.get('url')
        
        return media_info
    
    @staticmethod
    def _extract_sender_phone(remote_jid: str, participant: Optional[str] = None) -> str:
        """Extract clean phone number from WhatsApp JID."""
        # For group messages, use participant
        if participant:
            jid = participant
        else:
            jid = remote_jid
        
        # Extract phone number (before @)
        phone = jid.split('@')[0]
        
        # Remove any non-numeric characters
        return ''.join(filter(str.isdigit, phone))
    
    @staticmethod
    def normalize(
        event: EvolutionWebhookEvent,
        tenant_context: TenantContext,
        validation_status: Dict[str, bool]
    ) -> Optional[NormalizedMessage]:
        """
        Normalize Evolution API event to unified message format.
        
        Args:
            event: Validated Evolution API webhook event
            tenant_context: Verified tenant context
            validation_status: Security validation results
            
        Returns:
            NormalizedMessage if successful, None otherwise
        """
        try:
            # Extract key data
            key = event.data.key
            message = event.data.message
            
            # Determine message type
            message_dict = message.dict(exclude_none=True)
            message_type = MessageNormalizer._detect_message_type(message_dict)
            
            # Extract text content
            text = MessageNormalizer._extract_message_text(message_dict)
            
            # Extract media info
            media_info = MessageNormalizer._extract_media_info(message_dict, message_type)
            
            # Create content object
            content = MessageContent(
                text=text,
                media_url=media_info.get('media_url'),
                caption=media_info.get('caption'),
                mime_type=media_info.get('mime_type'),
                file_name=media_info.get('file_name')
            )
            
            # Extract sender phone
            sender_phone = MessageNormalizer._extract_sender_phone(
                key.remoteJid,
                key.participant
            )
            
            # Metadata
            is_group = key.remoteJid.endswith('@g.us')
            metadata = MessageMetadata(
                is_group=is_group,
                group_id=key.remoteJid if is_group else None,
                from_me=key.fromMe,
                forwarded=False,  # Would need to detect from message flags
                quoted_message_id=None  # Would extract from contextInfo
            )
            
            # Security info
            security = MessageSecurity(
                validated_at=datetime.utcnow().isoformat(),
                validation_passed=all(validation_status.values()),
                instance_verified=validation_status.get('instance_verified', False),
                tenant_resolved=validation_status.get('tenant_resolved', False),
                phone_ownership_verified=validation_status.get('phone_verified', False)
            )
            
            # Source info
            source = MessageSourceModel(
                platform='evolution_api',
                instance_id=event.instance,
                raw_event=event.dict()
            )
            
            # Timestamp
            timestamp = event.data.messageTimestamp or int(datetime.utcnow().timestamp())
            
            # Create normalized message
            normalized = NormalizedMessage(
                message_id=key.id,
                tenant_id=tenant_context.tenant_id,
                user_id=tenant_context.user_id,
                sender_phone=sender_phone,
                sender_name=event.data.pushName,
                message_type=message_type,
                content=content,
                timestamp=timestamp,
                source=source,
                metadata=metadata,
                security=security
            )
            
            logger.info(
                f"Message normalized successfully: {key.id}",
                message_id=key.id,
                tenant_id=tenant_context.tenant_id,
                user_id=tenant_context.user_id,
                message_type=message_type.value
            )
            
            return normalized
            
        except ValidationError as e:
            logger.error(
                f"Validation error during normalization: {str(e)}",
                tenant_id=tenant_context.tenant_id,
                details={'errors': e.errors()}
            )
            return None
        except Exception as e:
            logger.error(
                f"Unexpected error during normalization: {str(e)}",
                tenant_id=tenant_context.tenant_id,
                details={'error_type': type(e).__name__}
            )
            return None
    
    @staticmethod
    def should_process_event(event_type: str) -> bool:
        """Determine if event type should be processed."""
        processable_events = [
            'messages.upsert',
            # Add other event types as needed
        ]
        return event_type in processable_events
