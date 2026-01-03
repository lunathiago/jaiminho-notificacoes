"""
Example: Integrating LangGraph Orchestrator with Webhook Handler

This example shows how to integrate the MessageProcessingOrchestrator
into the main webhook handler pipeline.
"""

import asyncio
from jaiminho_notificacoes.persistence.models import (
    NormalizedMessage,
    ProcessingDecision
)
from jaiminho_notificacoes.processing.orchestrator import get_orchestrator
from jaiminho_notificacoes.outbound.sendpulse import SendPulseNotifier
from jaiminho_notificacoes.persistence.dynamodb import DynamoDBClient


async def process_webhook_message(message: NormalizedMessage):
    """
    Main webhook message processing pipeline.
    
    Flow:
    1. Message already validated for tenant isolation
    2. Get orchestrator and process
    3. Route based on final decision
    4. Persist processing result for audit
    """
    
    # Get orchestrator (singleton)
    orchestrator = get_orchestrator()
    
    # Process message through workflow
    # This will:
    # - Execute Rule Engine (deterministic)
    # - Call LLM Agent only if UNDECIDED
    # - Classify and route
    # - Generate complete audit trail
    processing_result = await orchestrator.process(message)
    
    print(f"Processing Result:")
    print(f"  Message ID: {processing_result.message_id}")
    print(f"  Tenant ID: {processing_result.tenant_id}")
    print(f"  User ID: {processing_result.user_id}")
    print(f"  Decision: {processing_result.decision.value}")
    print(f"  Rule Engine: {processing_result.rule_engine_decision}")
    print(f"  LLM Used: {processing_result.llm_used}")
    print(f"  Audit Steps: {len(processing_result.audit_trail)}")
    
    # Route based on decision
    if processing_result.decision == ProcessingDecision.IMMEDIATE:
        await send_immediate_notification(message, processing_result)
    
    elif processing_result.decision == ProcessingDecision.DIGEST:
        await add_to_daily_digest(message, processing_result)
    
    elif processing_result.decision == ProcessingDecision.SPAM:
        await filter_as_spam(message, processing_result)
    
    # Always persist the result for audit trail
    await persist_processing_result(message, processing_result)


async def send_immediate_notification(message: NormalizedMessage, processing_result):
    """Send immediate notification via SendPulse."""
    
    try:
        notifier = SendPulseNotifier()
        
        # Build notification
        notification = {
            "recipient_phone": message.sender_phone,
            "user_id": message.user_id,
            "tenant_id": message.tenant_id,
            "message_content": message.content.text or message.content.caption or "[Mídia]",
            "priority": "HIGH",
            "urgency_score": processing_result.rule_confidence,
            "processing_metadata": {
                "decision": processing_result.decision.value,
                "rule": processing_result.rule_engine_decision,
                "llm_used": processing_result.llm_used
            }
        }
        
        # Send via SendPulse
        result = await notifier.send_notification(notification)
        
        print(f"✓ Sent immediate notification: {result}")
        
    except Exception as e:
        print(f"✗ Failed to send notification: {e}")
        raise


async def add_to_daily_digest(message: NormalizedMessage, processing_result):
    """Add message to daily digest queue."""
    
    try:
        db = DynamoDBClient()
        
        # Store in digest table
        digest_entry = {
            "message_id": message.message_id,
            "user_id": message.user_id,
            "tenant_id": message.tenant_id,
            "sender_phone": message.sender_phone,
            "content": message.content.text or message.content.caption or "[Mídia]",
            "message_type": message.message_type.value,
            "urgency_decision": processing_result.rule_engine_decision,
            "timestamp": message.timestamp,
            "processing_decision": processing_result.decision.value,
            "ttl": int(time.time()) + (86400 * 7)  # 7 days
        }
        
        await db.put_item(
            table_name="jaiminho-digest-messages",
            item=digest_entry
        )
        
        print(f"✓ Added to daily digest: {message.message_id}")
        
    except Exception as e:
        print(f"✗ Failed to add to digest: {e}")
        raise


async def filter_as_spam(message: NormalizedMessage, processing_result):
    """Filter message as spam."""
    
    try:
        db = DynamoDBClient()
        
        # Log spam message
        spam_entry = {
            "message_id": message.message_id,
            "user_id": message.user_id,
            "tenant_id": message.tenant_id,
            "sender_phone": message.sender_phone,
            "content": message.content.text or message.content.caption,
            "reason": "Identified as spam by classification agent",
            "timestamp": message.timestamp,
        }
        
        await db.put_item(
            table_name="jaiminho-spam-messages",
            item=spam_entry
        )
        
        print(f"✓ Filtered as spam: {message.message_id}")
        
    except Exception as e:
        print(f"✗ Failed to filter spam: {e}")
        raise


async def persist_processing_result(message: NormalizedMessage, processing_result):
    """Persist processing result for audit trail."""
    
    try:
        db = DynamoDBClient()
        
        # Store processing result
        result_entry = {
            "message_id": message.message_id,
            "user_id": message.user_id,
            "tenant_id": message.tenant_id,
            "decision": processing_result.decision.value,
            "rule_engine_decision": processing_result.rule_engine_decision,
            "rule_confidence": processing_result.rule_confidence,
            "llm_used": processing_result.llm_used,
            "audit_trail": processing_result.audit_trail,
            "processed_at": processing_result.processed_at,
            "ttl": int(time.time()) + (86400 * 30)  # 30 days retention
        }
        
        await db.put_item(
            table_name="jaiminho-processing-results",
            item=result_entry
        )
        
        print(f"✓ Persisted processing result: {message.message_id}")
        
    except Exception as e:
        print(f"✗ Failed to persist result: {e}")
        raise


# Example usage in AWS Lambda handler
async def lambda_handler(event, context):
    """AWS Lambda handler integrating the orchestrator."""
    
    try:
        # Parse and validate message (already done by webhook handler)
        message = parse_webhook_message(event)
        
        # Validate tenant isolation (already done by tenant middleware)
        message = await validate_tenant_isolation(message)
        
        # Process through orchestrator
        await process_webhook_message(message)
        
        return {
            "statusCode": 200,
            "body": json.dumps({"status": "processed"})
        }
        
    except Exception as e:
        print(f"Error processing webhook: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }


if __name__ == "__main__":
    import time
    
    # Example: Create a test message
    from jaiminho_notificacoes.persistence.models import (
        MessageContent,
        MessageMetadata,
        MessageSecurity,
        MessageSource,
        MessageType
    )
    from datetime import datetime
    
    test_message = NormalizedMessage(
        message_id="msg-example-001",
        tenant_id="tenant-demo",
        user_id="user-demo",
        sender_phone="5511987654321",
        sender_name="Example Sender",
        message_type=MessageType.TEXT,
        content=MessageContent(text="PIX de R$ 500,00 recebido com sucesso"),
        timestamp=int(datetime.now().timestamp()),
        source=MessageSource(
            platform="wapi",
            instance_id="instance-demo"
        ),
        metadata=MessageMetadata(is_group=False, from_me=False),
        security=MessageSecurity(
            validated_at=datetime.now().isoformat(),
            validation_passed=True,
            instance_verified=True,
            tenant_resolved=True,
            phone_ownership_verified=True
        )
    )
    
    # Run example
    print("=" * 60)
    print("LangGraph Orchestrator Example")
    print("=" * 60)
    
    # Note: In production, use AWS Lambda or async server
    # asyncio.run(process_webhook_message(test_message))
