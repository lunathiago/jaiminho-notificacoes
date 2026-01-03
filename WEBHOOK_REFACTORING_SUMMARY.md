# W-API Webhook Handler - Refactoring Summary

## ✅ Refactoring Complete

The webhook handler has been refactored to support W-API exclusively with reinforced security for instance validation, user resolution, and tenant isolation.

---

## 🔐 Security Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│ W-API WEBHOOK RECEIVED                                          │
│ from: wapi.example.com/webhook                                  │
└──────────────────────────────┬──────────────────────────────────┘
                               ↓
                    ┌──────────────────────┐
                    │ [1] SCHEMA VALIDATE  │
                    │ WAPIWebhookEvent     │
                    │ ✓ instance           │
                    │ ✓ event              │
                    │ ✓ data               │
                    └──────┬──────────────┘
                           │
                  REJECT if ✗ Invalid JSON
                  REJECT if ✗ Missing fields
                           │
                           ↓
         ┌─────────────────────────────────────────┐
         │ [2] INSTANCE AUTHENTICATION             │
         │ wapi_instance_id → DynamoDB lookup      │
         │ WAPIInstanceRepository.get_by_instance()│
         └──────┬──────────────────────────────────┘
                │
       REJECT if ✗ Unknown
       REJECT if ✗ Inactive
                │
                ↓
    ┌───────────────────────────────┐
    │ [3] API KEY VERIFICATION      │
    │ Hash SHA-256(api_key)         │
    │ Compare with stored hash      │
    └──────┬────────────────────────┘
           │
   REJECT if ✗ Mismatch
           │
           ↓
    ┌───────────────────────────────┐
    │ [4] STATUS CHECK              │
    │ Must be: active|suspended     │
    └──────┬────────────────────────┘
           │
   REJECT if ✗ Disabled/Unknown
           │
           ↓
    ┌────────────────────────────────────┐
    │ [5] PHONE OWNERSHIP VALIDATION     │
    │ Extract sender phone from event    │
    │ Compare with instance's phone      │
    └──────┬─────────────────────────────┘
           │
   REJECT if ✗ Phone not owned
           │
           ↓
    ┌────────────────────────────────────┐
    │ [6] CROSS-TENANT DETECTION        │
    │ Detect payload overrides           │
    └──────┬─────────────────────────────┘
           │
   REJECT if ✗ Cross-tenant attempt
           │
           ↓
    ┌─────────────────────────────────────────┐
    │ ✅ ALL VALIDATIONS PASSED              │
    │ Resolve: tenant_id, user_id (internal) │
    │ Create: TenantContext                   │
    └──────┬────────────────────────────────┘
           │
           ↓
┌──────────────────────────────────────────────┐
│ [7] NORMALIZE & PROCESS                     │
│ Downstream: Classification, Urgency, Digest │
│ (no changes needed)                         │
└──────────────────────────────────────────────┘
```

---

## 📋 Changes by Component

### WebhookSecurityValidator

| Aspect | Before | After |
|--------|--------|-------|
| **Description** | Generic validator | "for W-API only" |
| **Validation** | Generic schema | Explicit W-API schema |
| **Error logging** | Basic | Error type classification |
| **Error message** | Generic | "Invalid W-API payload format" |

### MessageIngestionHandler.process_webhook()

| Aspect | Before | After |
|--------|--------|-------|
| **Field naming** | `instance_id` | `wapi_instance_id` |
| **Logging** | Basic context | Source + sender phone |
| **Rejection logging** | Simple errors | Detailed context + failure types |
| **User resolution** | Not explicit | "user_id resolved internally" |
| **Log metadata** | Basic | Includes `source='wapi'`, `wapi_instance_id` |

---

## 🔒 Security Guarantees

### 1. W-API Only
✅ Accepts only W-API schema  
✅ Rejects all other formats  
✅ No Evolution API fallback  

### 2. Instance Validation
✅ Unknown instance → 403  
✅ Inactive instance → 403  
✅ Looks up in WAPIInstanceRepository (1:1 mapping)  
✅ Never trusts instance_id from payload  

### 3. Phone Ownership
✅ Sender phone checked against instance  
✅ Rejects phones owned by different user  
✅ Audit logs all phone validation failures  

### 4. User Resolution
✅ Never trusts user_id from payload  
✅ Always resolves internally from instance mapping  
✅ User explicitly logged as "resolved internally"  

### 5. Cross-Tenant Protection
✅ Detects and rejects cross-tenant attempts  
✅ Compares payload tenant_id with verified tenant_id  
✅ Comprehensive audit logging  

### 6. Audit Trail
✅ All rejections logged with context  
✅ Sender phone included in logs  
✅ Failure reasons enumerated  
✅ Generic error message to prevent info leakage  

---

## 🚀 Behavior Examples

### ✅ Valid Webhook
```json
{
  "instance": "user-123-instance",
  "event": "messages.upsert",
  "apikey": "hashed-key-value",
  "data": { "key": { "remoteJid": "5511987654321@s.whatsapp.net" }, ... }
}
```
**Result:** 200 OK → Message processed → Added to queue  
**Logs:** "W-API instance validated successfully - user_id resolved internally"

### ❌ Unknown Instance
```json
{ "instance": "unknown-instance-999", ... }
```
**Result:** 403 Forbidden  
**Logs:** "W-API instance validation failed - webhook rejected" + instance not found

### ❌ Wrong API Key
```json
{ "instance": "user-123-instance", "apikey": "wrong-key", ... }
```
**Result:** 403 Forbidden  
**Logs:** "W-API instance validation failed - webhook rejected" + API key mismatch

### ❌ Phone Ownership Violation
```json
{
  "instance": "user-123-instance",  // belongs to user A
  "data": { "key": { "remoteJid": "5522999999999@s.whatsapp.net" }, ... }  // belongs to user B
}
```
**Result:** 403 Forbidden  
**Logs:** "W-API instance validation failed - webhook rejected" + phone ownership failed

### ❌ Cross-Tenant Attempt
```json
{
  "instance": "user-123-instance",
  "tenant_id": "different-tenant",  // Payload tries to override
  ...
}
```
**Result:** 403 Forbidden  
**Logs:** "W-API instance validation failed - webhook rejected" + cross-tenant attempt

---

## 📊 Audit Log Examples

### Success
```
level: INFO
event: message_processed
message_id: msg_abc123
tenant_id: tenant_xyz
user_id: user_456
message_type: text
source: wapi                    ← Source attribution
wapi_instance_id: inst_123      ← Instance tracking
```

### Rejection - Unknown Instance
```
level: WARNING
event: security_validation_failed
reason: W-API instance validation failed - webhook rejected
instance_id: unknown-instance
details: {
  "errors": {"instance_id": "Invalid or unauthorized instance"},
  "sender_phone": "5511987654321",
  "validation_failures": ["instance_id"]
}
```

### Rejection - Phone Ownership
```
level: WARNING
event: security_validation_failed
reason: W-API instance validation failed - webhook rejected
instance_id: user-123-instance
details: {
  "errors": {"phone_ownership": "Phone does not belong to this instance"},
  "sender_phone": "5522999999999",
  "validation_failures": ["phone_ownership"]
}
```

---

## ✔️ No Downstream Changes Required

All downstream components remain unchanged:

| Component | Status |
|-----------|--------|
| Message Normalizer | ✅ No changes |
| Classification Agent | ✅ No changes |
| Urgency Engine | ✅ No changes |
| Digest Generator | ✅ No changes |
| Learning Agent | ✅ No changes |
| SendPulse Adapter | ✅ No changes |
| Feedback Handler | ✅ No changes |

Reason: They all receive the same `NormalizedMessage` and verified `TenantContext`

---

## 🧪 Testing Checklist

### Validation Tests
- [ ] ✅ Valid W-API webhook → 200
- [ ] ✅ Invalid JSON → 400
- [ ] ✅ Missing W-API fields → 400
- [ ] ✅ Unknown instance → 403
- [ ] ✅ Inactive instance → 403
- [ ] ✅ Wrong API key → 403
- [ ] ✅ Phone not owned → 403
- [ ] ✅ Cross-tenant attempt → 403

### Security Tests
- [ ] ✅ Payload user_id ignored (internal resolution used)
- [ ] ✅ Instance lookup uses DynamoDB (not payload)
- [ ] ✅ Phone validation compares with registered phone
- [ ] ✅ Rejection messages don't leak details
- [ ] ✅ All rejections logged for audit

### Integration Tests
- [ ] ✅ End-to-end webhook → message → processing queue
- [ ] ✅ TenantContext propagates to downstream
- [ ] ✅ Message logs include source and instance ID
- [ ] ✅ No Evolution API requests attempted

---

## 📚 Documentation

- [WEBHOOK_HANDLER_REFACTORING.md](WEBHOOK_HANDLER_REFACTORING.md) - Detailed refactoring guide
- [WAPI_INSTANCES_MIGRATION.md](WAPI_INSTANCES_MIGRATION.md) - Data model changes
- [docs/WEBHOOK_HANDLER.md](docs/WEBHOOK_HANDLER.md) - Handler usage and examples
- [docs/TENANT_ISOLATION.md](docs/TENANT_ISOLATION.md) - Tenant isolation architecture

---

## 🎯 Summary

**What changed:**
- ✅ W-API-only schema validation
- ✅ Enhanced instance validation with repository
- ✅ Improved audit logging for all rejections
- ✅ Explicit user_id internal resolution
- ✅ Better error messages and logging

**What didn't change:**
- ✅ Downstream business logic (all compatible)
- ✅ Message normalization
- ✅ Processing pipeline
- ✅ TenantContext structure

**Security outcome:**
- ✅ No unknown instances accepted
- ✅ No invalid phones accepted
- ✅ No cross-tenant access possible
- ✅ Complete audit trail
- ✅ Zero information leakage in errors
