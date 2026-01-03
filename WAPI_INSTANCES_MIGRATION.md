# W-API Instances Migration Guide

## Summary of Changes

This document outlines the data model and infrastructure changes to replace `evolution_instances` with `wapi_instances`, enforcing strict one-to-one ownership and comprehensive tenant isolation.

## Data Model Changes

### Previous Model
The system previously lacked explicit mapping for Evolution API instances.

### New Model

#### WAPIInstance (Dataclass)
Renamed from `TenantInstance` to clarify its purpose and enforce user-scoped ownership:

```python
@dataclass
class WAPIInstance:
    """User-scoped W-API instance mapping with strict ownership."""
    tenant_id: str              # FK to tenant
    user_id: str                # PK - scoped access
    wapi_instance_id: str       # PK - unique identifier from W-API
    instance_name: str          # Display name
    phone_number: str           # Associated WhatsApp phone
    status: str                 # 'active', 'suspended', 'disabled'
    api_key_hash: str           # SHA-256 hash for security
    created_at: datetime        # Automatic
    updated_at: datetime        # Automatic
    metadata: Dict[str, Any]    # Extra fields
```

**Key Properties:**
- ✅ Each `wapi_instance_id` maps to exactly one `user_id`
- ✅ Each `wapi_instance_id` maps to exactly one `tenant_id`
- ✅ Composite primary key: `(user_id, wapi_instance_id)`
- ✅ Global secondary index on `wapi_instance_id` for webhook resolution
- ✅ All queries scoped by `user_id` to prevent cross-tenant access

## Repository: WAPIInstanceRepository

Located in `src/jaiminho_notificacoes/persistence/dynamodb.py`

### Methods

#### `get_by_instance_id(wapi_instance_id: str) -> Optional[WAPIInstance]`
- **Use case:** Webhook resolution
- **Query:** GSI lookup
- **Returns:** Instance mapping or None

#### `get_for_user(user_id: str, wapi_instance_id: str) -> Optional[WAPIInstance]`
- **Use case:** Fetch with user scoping
- **Query:** Point get with primary key
- **Security:** Always requires `user_id`

#### `list_for_user(user_id: str) -> List[WAPIInstance]`
- **Use case:** Enumerate user's instances
- **Query:** Query all items for `user_id`
- **Security:** Strictly scoped by partition key

#### `create_instance(instance: WAPIInstance) -> bool`
- **Use case:** Provision new instance
- **Ownership checks:** 
  - Verify no other user owns the `wapi_instance_id`
  - Verify no other tenant owns the `wapi_instance_id`
- **Atomicity:** Conditional write

#### `update_status(user_id: str, wapi_instance_id: str, status: str) -> bool`
- **Use case:** Activate/suspend instance
- **Ownership:** Scoped by `user_id`
- **Atomicity:** Condition requires existence

#### `delete_instance(user_id: str, wapi_instance_id: str) -> bool`
- **Use case:** Remove instance
- **Ownership:** Scoped by `user_id`
- **Atomicity:** Condition requires existence

## Infrastructure Changes

### DynamoDB Tables

#### New Table: `wapi_instances`
```
Table Name: {env}-jaiminho-wapi-instances
Billing Mode: PAY_PER_REQUEST
Region: As configured in Terraform

Primary Key:
  - Partition Key: user_id (String)
  - Sort Key: wapi_instance_id (String)

Global Secondary Index:
  - Name: InstanceLookupIndex
  - Hash Key: wapi_instance_id
  - Range Key: user_id
  - Projection: ALL

Point-in-time Recovery: Enabled in production
Server-side Encryption: Enabled
```

### Environment Variables

**Lambda Functions (all):**
```bash
DYNAMODB_WAPI_INSTANCES_TABLE=jaiminho-{env}-wapi-instances
DYNAMODB_WAPI_INSTANCE_GSI=InstanceLookupIndex
```

### IAM Permissions

All Lambda functions now have the following permissions on `wapi_instances`:
- `dynamodb:GetItem`
- `dynamodb:Query`
- `dynamodb:PutItem`
- `dynamodb:UpdateItem`
- `dynamodb:DeleteItem`

Resource paths include both table and index:
```
- arn:aws:dynamodb:REGION:ACCOUNT:table/TABLE_NAME
- arn:aws:dynamodb:REGION:ACCOUNT:table/TABLE_NAME/index/*
```

## Tenant Resolution Flow

When processing a webhook from W-API:

```
1. Extract wapi_instance_id from webhook
   ↓
2. Query InstanceLookupIndex to resolve ownership
   wapi_instance_id → (user_id, tenant_id)
   ↓
3. Verify API key against stored hash
   ↓
4. Check instance status (active/suspended)
   ↓
5. Validate phone number ownership
   ↓
6. Create TenantContext with verified (tenant_id, user_id)
   ↓
7. All downstream operations scoped to this context
```

**Security guarantees:**
- ✅ Never trust `user_id` from payload
- ✅ Only resolve from database
- ✅ Always validate API key
- ✅ Cannot be spoofed or forged
- ✅ Prevents cross-tenant access

## Code Changes

### Models
- **Renamed:** `TenantInstance` → `WAPIInstance`
- **Updated fields:** `instance_id` → `wapi_instance_id`

### Tenant Resolution
- **File:** `src/jaiminho_notificacoes/core/tenant.py`
- **Changes:**
  - Replaced direct DynamoDB table access with `WAPIInstanceRepository`
  - Removed `os.getenv('DYNAMODB_TENANTS_TABLE')`
  - Added `WAPIInstanceRepository()` initialization
  - Refactored `resolve_from_instance()` to use repository methods

### Documentation
- **File:** `docs/WEBHOOK_HANDLER.md`
- **Changes:**
  - Updated env var from `DYNAMODB_TENANTS_TABLE` → `DYNAMODB_WAPI_INSTANCES_TABLE`

## Migration Checklist

For existing deployments:

- [ ] Deploy updated Lambda code (models + repository + tenant.py)
- [ ] Apply Terraform changes to create new DynamoDB table
- [ ] Migrate existing instance mappings to new table
  ```bash
  # Script or manual process to transfer data
  # Old schema → New schema with wapi_instance_id, user_id, tenant_id
  ```
- [ ] Update environment variables in Lambda configs
- [ ] Update IAM policies to grant wapi_instances access
- [ ] Smoke test webhook processing with sample payloads
- [ ] Verify logs show successful tenant resolution
- [ ] Monitor for cross-tenant access attempts (should be zero)

## Security Properties

### One-to-One Ownership
- Each W-API instance is owned by exactly one user
- Each W-API instance is bound to exactly one tenant
- Enforced at write-time via:
  - Composite key: `(user_id, wapi_instance_id)`
  - GSI constraint: unique `wapi_instance_id`
  - Application-level validation in `create_instance()`

### No Cross-Tenant Access
- All reads scoped by `user_id` (partition key)
- All writes require `user_id`
- Query operations include `KeyConditionExpression`
- DynamoDB cannot return items outside partition

### API Key Validation
- Stored as SHA-256 hash (one-way)
- Compared on every webhook
- Timing-attack resistant (constant-time comparison)

### Referential Integrity
- Foreign key to `tenant_id` validated in Python
- Foreign key to `user_id` inherent in schema
- Status enum enforced in application

## Rollback Plan

If issues arise:

1. Revert code changes (restore old `TenantResolver`)
2. Keep both tables active temporarily
3. Update Lambda to read from old table
4. Investigate issues
5. Re-apply migration after fixes

**No data loss:** Old table remains until explicitly deleted.

## Monitoring

Watch for these metrics:

```
CloudWatch Logs:
- tenant.resolution_success (should be 100%)
- tenant.resolution_failure (should be 0)
- tenant.cross_tenant_attempt (should be 0)

DynamoDB:
- wapi_instances.UserConsumedWriteCapacity
- wapi_instances.InstanceLookupIndex.Query (webhook resolution)
- wapi_instances.ConsumedReadCapacity (should spike during webhook ingestion)
```

## References

- [AWS DynamoDB Best Practices](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/best-practices.html)
- [DynamoDB Query and Scan](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.html)
- [Tenant Isolation Architecture](docs/TENANT_ISOLATION.md)
- [Webhook Security](docs/WEBHOOK_HANDLER.md)
