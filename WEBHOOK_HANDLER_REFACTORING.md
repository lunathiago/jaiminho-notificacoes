# W-API Webhook Handler Refactoring

## Summary

The webhook handler has been refactored to exclusively support W-API and enforce strict security requirements for instance validation, user resolution, and tenant isolation.

## Changes Overview

### File: `src/jaiminho_notificacoes/lambda_handlers/ingest_whatsapp.py`

#### 1. WebhookSecurityValidator - W-API Only Schema Enforcement

**Changes:**
- Updated docstring to explicitly state "Validates webhook authenticity and security for W-API only"
- Enhanced `validate_request()` to clarify W-API schema validation
- Added explicit security checks documentation
- Improved error logging with error type classification
- Returns clearer error message: "Invalid W-API payload format"

**Security enforcement:**
```python
# Only accepts W-API schema
webhook_event = WAPIWebhookEvent(**payload)  # Validates:
#  - instance (wapi_instance_id)
#  - event (allowed event types)
#  - data (W-API message format)
```

#### 2. MessageIngestionHandler - W-API Instance Resolution Pipeline

**Changes:**
- Renamed field reference: `instance_id` → `wapi_instance_id` for clarity
- Enhanced instance extraction logging with sender phone info
- Updated validation pipeline documentation
- Improved rejection logging with detailed context

**Key updates:**

```python
# Extract W-API identifiers (step 1)
wapi_instance_id = webhook_event.instance      # Required W-API field
api_key = webhook_event.apikey                  # For authentication
sender_remote_jid = webhook_event.data.key.remoteJid  # Phone to validate

# Step 2-5: Complete W-API security validation
tenant_context, validation_errors = await self.middleware.validate_and_resolve(
    instance_id=wapi_instance_id,
    api_key=api_key,
    sender_phone=sender_remote_jid,
    payload=webhook_event.dict()
)
```

**Rejection audit logging:**
- Logs all validation failures with context
- Includes sender phone in rejection details
- Enumerates all validation failure types
- Returns generic error message to prevent information leakage

#### 3. Tenant Context Resolution - Internal Only

**Changes:**
- Enhanced logging to clarify "user_id resolved internally"
- Commented each validation status field with source of verification:
  - `instance_verified`: Verified via `resolve_from_instance()`
  - `tenant_resolved`: Resolved from instance mapping
  - `phone_verified`: Verified via `validate_phone_ownership()`

**Security guarantee:**
```python
logger.info(
    f"W-API instance validated successfully - user_id resolved internally",
    user_id=tenant_context.user_id,
    tenant_id=tenant_context.tenant_id
)
# This ensures downstream processors know user_id is verified
```

#### 4. Message Processing Logging - Source Attribution

**Changes:**
- Added `source='wapi'` to successful message processing logs
- Added `wapi_instance_id` to message metadata in logs
- Ensures audit trail tracks W-API source

```python
logger.message_processed(
    message_id=normalized_message.message_id,
    tenant_id=tenant_context.tenant_id,
    user_id=tenant_context.user_id,
    message_type=normalized_message.message_type.value,
    source='wapi',                          # ← Source attribution
    wapi_instance_id=wapi_instance_id       # ← Instance tracking
)
```

## Security Pipeline Diagram

```
Webhook from W-API
    ↓
[1] Schema Validation
    - Validates WAPIWebhookEvent structure
    - Requires: instance, event, data
    ↓ REJECT if invalid JSON/schema
    
[2] Instance Authentication
    - Lookup wapi_instance_id in DynamoDB
    - Query WAPIInstanceRepository.get_by_instance_id()
    ↓ REJECT if unknown or inactive
    
[3] API Key Verification
    - Compare provided api_key (hashed) vs stored hash
    ↓ REJECT if mismatch
    
[4] Instance Status Check
    - Verify status is 'active' or 'suspended'
    ↓ REJECT if 'disabled' or unknown
    
[5] Phone Ownership Validation
    - Extract sender phone from remoteJid
    - Compare with instance's registered phone
    ↓ REJECT if different user_id owns phone
    
[6] Cross-Tenant Detection
    - Detect if payload contains conflicting tenant_id/user_id
    ↓ REJECT if cross-tenant attempt
    
✓ PASS - Create TenantContext
    - tenant_id: from instance mapping (verified)
    - user_id: from instance mapping (verified)
    - instance_id: from payload (validated)
    ↓
[7] Message Normalization & Processing
    - All downstream operations use verified context
    - No payload fields used for access control
```

## Rejection Scenarios & Audit Logging

### Scenario 1: Unknown Instance
```
webhook_event.instance = "unknown-instance-123"

Flow:
  resolve_from_instance() → get_by_instance_id() → None
  ↓
Logger output:
  logger.invalid_instance(
    instance_id="unknown-instance-123",
    reason='Instance not found in database'
  )
Response: 403 "Unauthorized: Invalid or inactive W-API instance"
```

### Scenario 2: API Key Mismatch
```
webhook_event.instance = "valid-instance"
webhook_event.apikey = "wrong-key"

Flow:
  Instance found in DB
  Hash provided key: sha256("wrong-key") ≠ stored_hash
  ↓
Logger output:
  logger.security_validation_failed(
    reason='API key mismatch',
    instance_id="valid-instance",
    details={'provided_hash': '...first16chars...'}
  )
Response: 403 "Unauthorized: Invalid or inactive W-API instance"
```

### Scenario 3: Phone Ownership Violation
```
webhook_event.instance = "valid-instance"
webhook_event.data.key.remoteJid = "5511987654321@s.whatsapp.net"  # Wrong user's phone
instance.phone_number = "5511912345678"  # Registered to different user

Flow:
  All authentication checks pass
  validate_phone_ownership() compares phones
  clean_phone (11987654321) ≠ clean_instance_phone (11912345678)
  ↓
Logger output:
  logger.security_validation_failed(
    reason='Phone ownership validation failed',
    instance_id="valid-instance",
    tenant_id="tenant_1",
    details={
      'sender_phone': '11987654321',
      'expected_phone': '11912345678'
    }
  )
Response: 403 "Unauthorized: Invalid or inactive W-API instance"
```

### Scenario 4: Cross-Tenant Attempt
```
webhook_event.instance = "valid-instance"
webhook_event.tenant_id = "different-tenant"  # Payload tries to override

Flow:
  Instance resolution succeeds → tenant_id: "actual-tenant"
  detect_cross_tenant_attempt() detects conflict
  ↓
Logger output:
  logger.cross_tenant_attempt(
    attempted_tenant="different-tenant",
    actual_tenant="actual-tenant",
    instance_id="valid-instance"
  )
Response: 403 "Unauthorized: Invalid or inactive W-API instance"
```

## No Downstream Business Logic Changes

The refactoring maintains complete backward compatibility with downstream processing:

✅ Message normalization (normalizer.py)
✅ Classification agent (processing/agents.py)
✅ Urgency engine (processing/urgency_engine.py)
✅ Digest generator (processing/digest_generator.py)
✅ Learning agent (processing/learning_agent.py)
✅ SendPulse adapter (outbound/sendpulse.py)
✅ Feedback handler (processing/feedback_handler.py)

All downstream components receive the same `NormalizedMessage` schema and `TenantContext` - no changes required.

## Verification Checklist

- ✅ Schema validation enforces W-API format only
- ✅ Instance lookup uses WAPIInstanceRepository
- ✅ API key validation with SHA-256 hash
- ✅ Phone ownership checked against instance registration
- ✅ Cross-tenant attempts detected and rejected
- ✅ All rejections logged with audit context
- ✅ user_id never trusted from payload
- ✅ user_id always resolved from instance mapping
- ✅ Rejection messages don't leak information
- ✅ Downstream logic unchanged
- ✅ No Evolution API compatibility maintained

## Testing Recommendations

### Unit Tests
- ✅ Unknown instance → 403
- ✅ Inactive instance → 403
- ✅ API key mismatch → 403
- ✅ Phone not owned → 403
- ✅ Cross-tenant attempt → 403
- ✅ Valid webhook → 200 + message queued
- ✅ Invalid JSON → 400
- ✅ Missing W-API fields → 400

### Integration Tests
- ✅ End-to-end webhook processing
- ✅ Audit log verification for rejections
- ✅ Downstream message processing
- ✅ Tenant context propagation

## Monitoring

Watch for these metrics in production:

```
Success metrics:
- webhook.processed (counter, should be high)
- webhook.success_rate (gauge, should be > 99%)

Security metrics:
- webhook.rejected.invalid_instance (counter, monitor for spikes)
- webhook.rejected.invalid_key (counter, monitor for attacks)
- webhook.rejected.phone_ownership (counter, monitor for usage errors)
- webhook.rejected.cross_tenant (counter, should be 0)

Latency:
- webhook.validation_duration_ms (histogram)
- webhook.end_to_end_duration_ms (histogram)
```

## References

- [WAPI_INSTANCES_MIGRATION.md](WAPI_INSTANCES_MIGRATION.md) - Instance model changes
- [docs/WEBHOOK_HANDLER.md](docs/WEBHOOK_HANDLER.md) - Handler documentation
- [docs/TENANT_ISOLATION.md](docs/TENANT_ISOLATION.md) - Tenant isolation architecture
