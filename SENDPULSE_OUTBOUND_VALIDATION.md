# SendPulse Outbound-Only Validation

**Status**: ✅ COMPLIANT (Refactored Jan 3, 2026)

## Policy: SendPulse is Strictly Outbound-Only

SendPulse WhatsApp adapter serves ONE purpose: **sending notifications**. It must never process inbound messages or webhooks.

---

## ✅ Compliance Checks

### 1. ✅ No Inbound Webhook Logic

**Status**: COMPLIANT

- ❌ **Removed**: `process_feedback_webhook.py` lambda handler
  - This file was attempting to receive button responses from SendPulse
  - **Reason**: SendPulse has NO webhook capability for button responses
  - **Replacement**: Use W-API webhooks only (via `ingest_whatsapp.py`)

- ✅ **Correct Flow**: 
  ```
  User clicks button on SendPulse message
         ↓
  User's WhatsApp client relays to W-API
         ↓
  W-API sends webhook to ingest_whatsapp.py (W-API handler)
         ↓
  Message normalized, user resolved via W-API instance
         ↓
  FeedbackHandler processes with W-API context
  ```

### 2. ✅ Single Official WhatsApp Number

**Status**: COMPLIANT

- **Implementation**: One WhatsApp number per tenant
- **Storage**: `SENDPULSE_SECRET_ARN` (AWS Secrets Manager)
- **Credentials Structure**:
  ```json
  {
    "client_id": "tenant_unique_client_id",
    "client_secret": "tenant_unique_secret",
    "api_url": "https://api.sendpulse.com"
  }
```
- **Access**: `SendPulseAuthenticator.get_credentials()` retrieves from Secrets Manager
- **Validation**: No per-user SendPulse configuration exists in codebase

**File**: [SendPulseAuthenticator](src/jaiminho_notificacoes/outbound/sendpulse.py#L200-L230)

### 3. ✅ Destination Phone Resolved via user_id

**Status**: COMPLIANT

- **Resolver**: `SendPulseUserResolver` class
- **Lookup Process**:
  1. Input: `tenant_id` + `user_id`
  2. Query: DynamoDB `jaiminho-user-profiles` table
  3. Get: `whatsapp_phone` field from user profile
  4. Cache: Phone cached locally (namespace: `{tenant_id}#{user_id}`)
  5. Return: Phone with country code, or None if not found

- **No Alternatives**:
  - ❌ Removed: `recipient_phone` override parameter
  - ✅ Enforced: ALL messages must resolve phone via user_id
  - ✅ Validated: Phone validation in `SendPulseMessage.validate()`

**File**: [SendPulseUserResolver](src/jaiminho_notificacoes/outbound/sendpulse.py#L258-L320)

### 4. ✅ No Per-User SendPulse Configuration

**Status**: COMPLIANT

- ✅ **No User-Level Config**: 
  - All SendPulse config is at tenant level
  - Retrieved from single Secrets Manager entry
  - No DynamoDB user-preferences for SendPulse

- ✅ **Immutable Phone Resolution**:
  - Phone comes from `whatsapp_phone` field in user profile
  - Cannot be overridden per-message
  - Cannot be configured per-tenant-user

- ✅ **Stateless Senders**:
  - `SendPulseUrgentNotifier`
  - `SendPulseDigestSender`
  - `SendPulseFeedbackSender`
  - Each is instantiated fresh, no shared state

**File**: [SendPulseManager.send_notification()](src/jaiminho_notificacoes/outbound/sendpulse.py#L733-L800)

---

## 📊 Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    SendPulse Manager                        │
│  (Outbound Notifications Only)                              │
└─────────────────────────────────────────────────────────────┘
              ↑                          ↑                    ↑
              │                          │                    │
    ┌─────────┴──────────┐   ┌──────────┴────────┐   ┌───────┴──────────┐
    │ Urgent Notifier    │   │ Digest Sender     │   │ Feedback Sender  │
    │ (immediate)        │   │ (scheduled)       │   │ (buttons)        │
    └─────────┬──────────┘   └──────────┬────────┘   └───────┬──────────┘
              │                          │                    │
              └──────────────┬───────────┴────────┬───────────┘
                             │                    │
              ┌──────────────┴─────┐              │
              │ SendPulseAuthent.  │              │
              │ (Get OAuth token)  │              │
              └──────────────┬─────┘              │
                             │                    │
        ┌────────────────────┴─────────────────┐  │
        │ Secrets Manager                      │  │
        │ SENDPULSE_SECRET_ARN                 │  │
        │ {client_id, client_secret, api_url} │  │
        └────────────────────────────────────┘  │
                                                 │
              ┌──────────────────────────────────┘
              │
    ┌─────────▼──────────────┐
    │ SendPulseUserResolver  │
    │ (Phone resolution)     │
    └─────────┬──────────────┘
              │
    ┌─────────▼──────────────────────┐
    │ DynamoDB User Profiles Table    │
    │ Key: tenant_id + user_id        │
    │ Get: whatsapp_phone             │
    └────────────────────────────────┘
```

---

## 🚫 What SendPulse CANNOT Do

1. ❌ Receive webhook events (no inbound)
2. ❌ Process button responses (no feedback receiving)
3. ❌ Store per-user configuration
4. ❌ Accept phone number overrides
5. ❌ Handle multiple WhatsApp numbers per tenant
6. ❌ Verify webhook signatures (no webhooks!)

---

## ✅ What SendPulse CAN Do

1. ✅ Send urgent alerts (HIGH priority, immediate)
2. ✅ Send daily digests (MEDIUM priority, scheduled)
3. ✅ Send interactive buttons (feedback collection)
4. ✅ Include media (images, videos)
5. ✅ Resolve user phone via DynamoDB
6. ✅ Emit CloudWatch metrics for monitoring
7. ✅ Support multi-tenant isolation

---

## 🔧 Feedback Flow (Correct)

```
User clicks button on SendPulse message
         │
         ├─→ Device WhatsApp client
         │
         └─→ User's W-API webhook endpoint
                 │
                 ├─→ ingest_whatsapp.py (W-API handler)
                 │
                 ├─→ MessageNormalizer
                 │
                 ├─→ FeedbackHandler.handle_webhook()
                 │
                 └─→ Learning Agent (update statistics)
```

**Critical**: Response comes from W-API, NOT SendPulse.

---

## 📝 Migration Notes

### Deprecated Files
- ❌ `process_feedback_webhook.py` - Now returns 501 Not Implemented
  - This was attempting to process SendPulse webhooks
  - SendPulse has NO webhook capability
  - Keep file for reference only

### Modified Files
- ✅ `sendpulse.py` - Removed `recipient_phone` override
  - Phone ALWAYS resolved via user_id
  - Enhanced documentation
  - Added enforcement in docstring

### Correct Integration Files
- ✅ `send_notifications.py` - Lambda for outbound
- ✅ `ingest_whatsapp.py` - Lambda for inbound (W-API only)

---

## 🧪 Verification Checklist

Run these checks to verify SendPulse outbound-only compliance:

```bash
# Check 1: No SendPulse inbound imports
grep -r "process_feedback_webhook" src/ --include="*.py" | grep -v "deprecated"
# Expected: Only in deprecated file or comments

# Check 2: No recipient_phone override in calls
grep -r "recipient_phone=" src/jaiminho_notificacoes/outbound/ --include="*.py"
# Expected: No matches (it's removed from parameter)

# Check 3: Verify user resolver is used
grep -r "resolve_phone" src/jaiminho_notificacoes/ --include="*.py" | grep "def\|await"
# Expected: Multiple matches in SendPulseManager

# Check 4: SendPulse only in outbound
find src/jaiminho_notificacoes/ingestion -name "*sendpulse*"
# Expected: No matches (SendPulse not in ingestion layer)
```

---

## 📚 Related Documentation

- [SendPulse Adapter](docs/SENDPULSE_ADAPTER.md)
- [SendPulse Integration](docs/SENDPULSE_INTEGRATION.md)
- [Webhook Handler](docs/WEBHOOK_HANDLER.md)
- [Feedback Handler](docs/FEEDBACK_HANDLER.md)

---

## ✅ Sign-Off

- **Validation Date**: January 3, 2026
- **Status**: COMPLIANT
- **Violations Found**: 2 (now fixed)
- **Risk Level**: LOW
- **Action Required**: None (refactoring complete)
