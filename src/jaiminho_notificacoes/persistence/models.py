"""Data models and schemas for storage."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, List
from pydantic import BaseModel, Field, validator


class MessageType(str, Enum):
    """Message content types."""
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    LOCATION = "location"
    CONTACT = "contact"
    UNKNOWN = "unknown"


class MessageSource(str, Enum):
    """Message source platforms."""
    EVOLUTION_API = "evolution_api"
    WHATSAPP_BUSINESS_API = "whatsapp_business_api"


class ProcessingDecision(str, Enum):
    """Final processing decision for a message."""
    IMMEDIATE = "immediate"  # Send via SendPulse immediately
    DIGEST = "digest"        # Add to daily digest
    SPAM = "spam"            # Filter out as spam


# Pydantic Models for Validation
class EvolutionMessageKey(BaseModel):
    """Evolution API message key."""
    remoteJid: str = Field(..., min_length=1)
    fromMe: bool
    id: str = Field(..., min_length=1)
    participant: Optional[str] = None

    @validator('remoteJid')
    def validate_remote_jid(cls, v):
        """Validate WhatsApp JID format."""
        if not (v.endswith('@s.whatsapp.net') or v.endswith('@g.us')):
            raise ValueError("Invalid WhatsApp JID format")
        return v


class EvolutionMessageContent(BaseModel):
    """Evolution API message content."""
    conversation: Optional[str] = None
    extendedTextMessage: Optional[Dict[str, Any]] = None
    imageMessage: Optional[Dict[str, Any]] = None
    videoMessage: Optional[Dict[str, Any]] = None
    documentMessage: Optional[Dict[str, Any]] = None
    audioMessage: Optional[Dict[str, Any]] = None


class EvolutionEventData(BaseModel):
    """Evolution API event data."""
    key: EvolutionMessageKey
    message: EvolutionMessageContent
    messageTimestamp: Optional[int] = None
    pushName: Optional[str] = None


class EvolutionWebhookEvent(BaseModel):
    """Evolution API webhook event."""
    instance: str = Field(..., min_length=1)
    event: str = Field(..., min_length=1)
    data: EvolutionEventData
    server_url: Optional[str] = None
    apikey: Optional[str] = None

    @validator('event')
    def validate_event_type(cls, v):
        """Validate event type."""
        allowed_events = [
            'messages.upsert',
            'messages.update',
            'message.revoked',
            'messages.delete',
            'connection.update'
        ]
        if v not in allowed_events:
            raise ValueError(f"Unsupported event type: {v}")
        return v


class MessageContent(BaseModel):
    """Normalized message content."""
    text: Optional[str] = None
    media_url: Optional[str] = None
    caption: Optional[str] = None
    mime_type: Optional[str] = None
    file_name: Optional[str] = None


class MessageMetadata(BaseModel):
    """Message metadata."""
    is_group: bool = False
    group_id: Optional[str] = None
    from_me: bool = False
    forwarded: bool = False
    quoted_message_id: Optional[str] = None


class MessageSecurity(BaseModel):
    """Message security validation status."""
    validated_at: str
    validation_passed: bool
    instance_verified: bool
    tenant_resolved: bool
    phone_ownership_verified: bool


class MessageSource(BaseModel):
    """Message source information."""
    platform: str = Field(..., pattern="^(evolution_api|whatsapp_business_api)$")
    instance_id: str
    raw_event: Optional[Dict[str, Any]] = None


class NormalizedMessage(BaseModel):
    """Normalized message after security validation."""
    message_id: str = Field(..., min_length=1)
    tenant_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    sender_phone: str = Field(..., pattern="^[0-9]{10,15}$")
    sender_name: Optional[str] = None
    message_type: MessageType
    content: MessageContent
    timestamp: int = Field(..., ge=0)
    source: MessageSource
    metadata: MessageMetadata = Field(default_factory=MessageMetadata)
    security: MessageSecurity
    
    # Classification fields (added by Classification Agent)
    classification_category: Optional[str] = None
    classification_summary: Optional[str] = None
    classification_routing: Optional[str] = None
    classification_confidence: Optional[float] = None

    class Config:
        use_enum_values = True


# Dataclasses for Database Storage
@dataclass
class TenantInstance:
    """Tenant Evolution API instance mapping."""
    tenant_id: str
    user_id: str
    instance_id: str
    instance_name: str
    phone_number: str
    status: str  # active, suspended, disabled
    api_key_hash: str
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MessageRecord:
    """Message storage record."""
    message_id: str
    tenant_id: str
    user_id: str
    sender_phone: str
    sender_name: Optional[str]
    message_type: str
    content: Dict[str, Any]
    timestamp: int
    source_platform: str
    source_instance_id: str
    is_group: bool
    group_id: Optional[str]
    from_me: bool
    status: str  # pending, processed, failed
    urgency_score: Optional[float] = None
    processed_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SecurityAuditLog:
    """Security audit log entry."""
    log_id: str
    event_type: str  # validation_failed, cross_tenant_attempt, invalid_instance
    severity: str  # low, medium, high, critical
    tenant_id: Optional[str]
    user_id: Optional[str]
    instance_id: Optional[str]
    remote_ip: Optional[str]
    details: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ProcessingResult:
    """Result of message processing through orchestration."""
    message_id: str
    tenant_id: str
    user_id: str
    decision: ProcessingDecision
    rule_engine_decision: Optional[str]  # urgent, not_urgent, undecided
    rule_confidence: float
    llm_used: bool
    audit_trail: List[Dict[str, Any]]
    processed_at: str


# Learning Agent Models


class FeedbackType(str, Enum):
    """Binary feedback on message urgency."""
    IMPORTANT = "important"
    NOT_IMPORTANT = "not_important"


@dataclass
class UserFeedbackRecord:
    """User feedback on message urgency (for database storage)."""
    feedback_id: str
    tenant_id: str
    user_id: str
    message_id: str
    sender_phone: str
    sender_name: Optional[str]
    feedback_type: str  # "important" or "not_important"
    message_category: Optional[str]
    was_interrupted: bool
    user_response_time_seconds: Optional[float]
    feedback_timestamp: int
    feedback_reason: Optional[str]
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class InterruptionStatisticsRecord:
    """Interruption statistics for sender/category/user level."""
    tenant_id: str
    user_id: str
    sender_phone: Optional[str] = None  # None = category or user level
    category: Optional[str] = None  # None = sender or user level

    # Feedback counters
    total_feedback_count: int = 0
    important_count: int = 0
    not_important_count: int = 0

    # System accuracy metrics
    correct_interrupts: int = 0
    incorrect_interrupts: int = 0
    correct_digests: int = 0
    missed_urgent: int = 0

    # Response time statistics
    avg_response_time_seconds: float = 0.0
    total_response_time_seconds: float = 0.0
    response_count: int = 0

    # Time window
    window_start_timestamp: int = 0
    window_end_timestamp: int = 0
    last_updated: datetime = field(default_factory=datetime.utcnow)
