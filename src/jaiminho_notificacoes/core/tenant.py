"""Tenant isolation and context management."""

import hashlib
import os
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
import boto3
from botocore.exceptions import ClientError

from .logger import get_logger

logger = get_logger(__name__)


@dataclass
class TenantContext:
    """Tenant context with verified information."""
    tenant_id: str
    user_id: str
    instance_id: str
    phone_number: str
    status: str
    
    def is_active(self) -> bool:
        """Check if tenant is active."""
        return self.status == 'active'
    
    def __post_init__(self):
        """Validate tenant context after initialization."""
        if not all([self.tenant_id, self.user_id, self.instance_id]):
            raise ValueError("All tenant context fields are required")


class TenantResolver:
    """Resolve and validate tenant information from instance_id."""
    
    def __init__(self):
        self.dynamodb = boto3.resource('dynamodb')
        self.rds_client = None  # Initialized on demand
        self._cache: Dict[str, TenantContext] = {}
        
        # Table names from environment
        self.tenants_table_name = os.getenv('DYNAMODB_TENANTS_TABLE')
        if not self.tenants_table_name:
            raise ValueError("DYNAMODB_TENANTS_TABLE environment variable not set")
        
        self.tenants_table = self.dynamodb.Table(self.tenants_table_name)
    
    def _hash_api_key(self, api_key: str) -> str:
        """Hash API key for secure storage comparison."""
        return hashlib.sha256(api_key.encode()).hexdigest()
    
    def _get_from_cache(self, instance_id: str) -> Optional[TenantContext]:
        """Get tenant context from cache."""
        return self._cache.get(instance_id)
    
    def _add_to_cache(self, instance_id: str, context: TenantContext):
        """Add tenant context to cache."""
        # Simple in-memory cache (consider Redis for production)
        if len(self._cache) > 1000:  # Prevent memory leak
            self._cache.clear()
        self._cache[instance_id] = context
    
    async def resolve_from_instance(
        self,
        instance_id: str,
        api_key: Optional[str] = None
    ) -> Optional[TenantContext]:
        """
        Resolve tenant and user from instance_id.
        
        This is the critical security function that:
        1. Validates instance_id exists in database
        2. Validates API key if provided
        3. Returns verified tenant_id and user_id
        4. NEVER trusts payload user_id
        
        Args:
            instance_id: W-API instance identifier
            api_key: Optional API key for additional validation
            
        Returns:
            TenantContext if valid, None otherwise
        """
        # Check cache first
        cached = self._get_from_cache(instance_id)
        if cached and cached.is_active():
            logger.debug(f"Tenant context found in cache for instance: {instance_id}")
            return cached
        
        try:
            # Query DynamoDB for instance mapping
            response = self.tenants_table.get_item(
                Key={'instance_id': instance_id}
            )
            
            if 'Item' not in response:
                logger.invalid_instance(
                    instance_id=instance_id,
                    reason='Instance not found in database'
                )
                return None
            
            item = response['Item']
            
            # Validate API key if provided
            if api_key:
                api_key_hash = self._hash_api_key(api_key)
                stored_hash = item.get('api_key_hash')
                
                if not stored_hash or api_key_hash != stored_hash:
                    logger.security_validation_failed(
                        reason='API key mismatch',
                        instance_id=instance_id,
                        details={'provided_hash': api_key_hash[:16]}
                    )
                    return None
            
            # Check status
            status = item.get('status', 'unknown')
            if status not in ('active', 'suspended'):
                logger.invalid_instance(
                    instance_id=instance_id,
                    reason=f'Invalid status: {status}'
                )
                return None
            
            # Create verified tenant context
            context = TenantContext(
                tenant_id=item['tenant_id'],
                user_id=item['user_id'],
                instance_id=instance_id,
                phone_number=item.get('phone_number', ''),
                status=status
            )
            
            # Cache for future requests
            self._add_to_cache(instance_id, context)
            
            logger.info(
                f"Tenant resolved successfully",
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                instance_id=instance_id
            )
            
            return context
            
        except ClientError as e:
            logger.error(
                f"DynamoDB error resolving tenant: {str(e)}",
                instance_id=instance_id,
                details={'error': str(e)}
            )
            return None
        except Exception as e:
            logger.error(
                f"Unexpected error resolving tenant: {str(e)}",
                instance_id=instance_id,
                details={'error_type': type(e).__name__}
            )
            return None
    
    def validate_phone_ownership(
        self,
        sender_phone: str,
        tenant_context: TenantContext
    ) -> bool:
        """
        Validate that sender phone belongs to the tenant's instance.
        
        This prevents cross-tenant message injection where:
        - Attacker has valid instance_id
        - But tries to send messages from another tenant's phone
        
        Args:
            sender_phone: Phone number from message
            tenant_context: Verified tenant context
            
        Returns:
            True if phone belongs to tenant, False otherwise
        """
        # Extract phone from WhatsApp JID format
        clean_phone = sender_phone.split('@')[0] if '@' in sender_phone else sender_phone
        
        # Check if it matches the instance's registered phone
        instance_phone = tenant_context.phone_number.replace('+', '')
        clean_instance_phone = instance_phone.split('@')[0] if '@' in instance_phone else instance_phone
        
        # For group messages, we need additional validation
        # For now, we validate that the message comes from the instance's phone
        is_valid = clean_phone == clean_instance_phone
        
        if not is_valid:
            logger.security_validation_failed(
                reason='Phone ownership validation failed',
                instance_id=tenant_context.instance_id,
                tenant_id=tenant_context.tenant_id,
                details={
                    'sender_phone': clean_phone,
                    'expected_phone': clean_instance_phone
                }
            )
        
        return is_valid
    
    def detect_cross_tenant_attempt(
        self,
        payload: Dict,
        verified_tenant_id: str
    ) -> bool:
        """
        Detect if payload contains cross-tenant attack indicators.
        
        Args:
            payload: Raw webhook payload
            verified_tenant_id: Tenant ID from instance resolution
            
        Returns:
            True if attack detected, False otherwise
        """
        # Check if payload tries to specify a different tenant/user
        payload_tenant = payload.get('tenant_id')
        payload_user = payload.get('user_id')
        
        if payload_tenant and payload_tenant != verified_tenant_id:
            logger.cross_tenant_attempt(
                attempted_tenant=payload_tenant,
                actual_tenant=verified_tenant_id,
                instance_id=payload.get('instance', 'unknown'),
                details={'payload_keys': list(payload.keys())}
            )
            return True
        
        if payload_user:
            # User ID should NEVER come from payload
            logger.security_event(
                event_type='suspicious_payload',
                severity='medium',
                message='Payload contains user_id field (should be resolved internally)',
                tenant_id=verified_tenant_id,
                details={'payload_user': payload_user}
            )
            # Not blocking, but logged for investigation
        
        return False


class TenantIsolationMiddleware:
    """Middleware to enforce tenant isolation in all operations."""
    
    def __init__(self):
        self.resolver = TenantResolver()
    
    async def validate_and_resolve(
        self,
        instance_id: str,
        api_key: Optional[str] = None,
        sender_phone: Optional[str] = None,
        payload: Optional[Dict] = None
    ) -> Tuple[Optional[TenantContext], Dict[str, str]]:
        """
        Complete validation and resolution pipeline.
        
        Returns:
            (TenantContext, errors_dict) tuple
            - TenantContext if all validations pass
            - errors_dict contains validation failure reasons
        """
        errors = {}
        
        # Step 1: Resolve tenant from instance_id
        tenant_context = await self.resolver.resolve_from_instance(
            instance_id=instance_id,
            api_key=api_key
        )
        
        if not tenant_context:
            errors['instance_id'] = 'Invalid or unauthorized instance'
            return None, errors
        
        # Step 2: Check tenant status
        if not tenant_context.is_active():
            errors['status'] = f'Tenant status is {tenant_context.status}'
            logger.security_validation_failed(
                reason=f'Inactive tenant status: {tenant_context.status}',
                instance_id=instance_id,
                tenant_id=tenant_context.tenant_id
            )
            return None, errors
        
        # Step 3: Validate phone ownership (if sender provided)
        if sender_phone:
            if not self.resolver.validate_phone_ownership(sender_phone, tenant_context):
                errors['phone_ownership'] = 'Phone does not belong to this instance'
                return None, errors
        
        # Step 4: Detect cross-tenant attempts
        if payload:
            if self.resolver.detect_cross_tenant_attempt(payload, tenant_context.tenant_id):
                errors['cross_tenant'] = 'Cross-tenant access attempt detected'
                return None, errors
        
        return tenant_context, {}

