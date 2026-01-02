"""Script to initialize tenant-instance mappings in DynamoDB.

This script helps bootstrap the tenant isolation system by creating
the initial mappings between Evolution API instances and tenants.

SECURITY CRITICAL: This mapping is the foundation of tenant isolation.
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime
from typing import Dict, Any

import boto3
from botocore.exceptions import ClientError


def hash_api_key(api_key: str) -> str:
    """Hash API key using SHA-256."""
    return hashlib.sha256(api_key.encode()).hexdigest()


def create_tenant_mapping(
    dynamodb_table_name: str,
    tenant_id: str,
    user_id: str,
    instance_id: str,
    instance_name: str,
    phone_number: str,
    api_key: str,
    status: str = "active",
    metadata: Dict[str, Any] = None
) -> bool:
    """
    Create a tenant-instance mapping in DynamoDB.
    
    Args:
        dynamodb_table_name: Name of the tenants table
        tenant_id: Unique tenant identifier
        user_id: User identifier (owner of the instance)
        instance_id: Evolution API instance ID
        instance_name: Human-readable instance name
        phone_number: WhatsApp phone number for the instance
        api_key: Evolution API key (will be hashed)
        status: Tenant status (active, suspended, disabled)
        metadata: Additional metadata
        
    Returns:
        True if successful, False otherwise
    """
    try:
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(dynamodb_table_name)
        
        # Hash the API key
        api_key_hash = hash_api_key(api_key)
        
        # Create item
        item = {
            'instance_id': instance_id,  # Partition key
            'tenant_id': tenant_id,
            'user_id': user_id,
            'instance_name': instance_name,
            'phone_number': phone_number,
            'api_key_hash': api_key_hash,
            'status': status,
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat(),
            'metadata': metadata or {}
        }
        
        # Put item
        table.put_item(Item=item)
        
        print(f"✅ Successfully created mapping for instance: {instance_id}")
        print(f"   Tenant: {tenant_id}")
        print(f"   User: {user_id}")
        print(f"   Phone: {phone_number}")
        print(f"   Status: {status}")
        
        return True
        
    except ClientError as e:
        print(f"❌ DynamoDB error: {e.response['Error']['Message']}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        return False


def list_tenant_mappings(dynamodb_table_name: str):
    """List all tenant-instance mappings."""
    try:
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(dynamodb_table_name)
        
        response = table.scan()
        items = response.get('Items', [])
        
        if not items:
            print("No tenant mappings found.")
            return
        
        print(f"\n📋 Found {len(items)} tenant mapping(s):\n")
        
        for item in items:
            print(f"Instance ID: {item['instance_id']}")
            print(f"  Tenant: {item['tenant_id']}")
            print(f"  User: {item['user_id']}")
            print(f"  Phone: {item['phone_number']}")
            print(f"  Status: {item['status']}")
            print(f"  Created: {item['created_at']}")
            print()
        
    except Exception as e:
        print(f"❌ Error listing mappings: {str(e)}")


def update_tenant_status(
    dynamodb_table_name: str,
    instance_id: str,
    new_status: str
) -> bool:
    """Update tenant status."""
    try:
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(dynamodb_table_name)
        
        table.update_item(
            Key={'instance_id': instance_id},
            UpdateExpression='SET #status = :status, updated_at = :updated',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': new_status,
                ':updated': datetime.utcnow().isoformat()
            }
        )
        
        print(f"✅ Updated instance {instance_id} status to: {new_status}")
        return True
        
    except ClientError as e:
        print(f"❌ Error updating status: {e.response['Error']['Message']}")
        return False


def main():
    """Main CLI interface."""
    parser = argparse.ArgumentParser(
        description='Manage tenant-instance mappings for Jaiminho Notificações'
    )
    
    parser.add_argument(
        '--table',
        required=True,
        help='DynamoDB table name (e.g., jaiminho-dev-tenants)'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Create mapping command
    create_parser = subparsers.add_parser('create', help='Create tenant mapping')
    create_parser.add_argument('--tenant-id', required=True, help='Tenant ID')
    create_parser.add_argument('--user-id', required=True, help='User ID')
    create_parser.add_argument('--instance-id', required=True, help='Evolution API instance ID')
    create_parser.add_argument('--instance-name', required=True, help='Instance name')
    create_parser.add_argument('--phone', required=True, help='WhatsApp phone number')
    create_parser.add_argument('--api-key', required=True, help='Evolution API key')
    create_parser.add_argument('--status', default='active', choices=['active', 'suspended', 'disabled'])
    create_parser.add_argument('--metadata', type=json.loads, help='Additional metadata (JSON)')
    
    # List mappings command
    subparsers.add_parser('list', help='List all tenant mappings')
    
    # Update status command
    status_parser = subparsers.add_parser('update-status', help='Update tenant status')
    status_parser.add_argument('--instance-id', required=True, help='Instance ID')
    status_parser.add_argument('--status', required=True, choices=['active', 'suspended', 'disabled'])
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Execute command
    if args.command == 'create':
        success = create_tenant_mapping(
            dynamodb_table_name=args.table,
            tenant_id=args.tenant_id,
            user_id=args.user_id,
            instance_id=args.instance_id,
            instance_name=args.instance_name,
            phone_number=args.phone,
            api_key=args.api_key,
            status=args.status,
            metadata=args.metadata
        )
        return 0 if success else 1
    
    elif args.command == 'list':
        list_tenant_mappings(args.table)
        return 0
    
    elif args.command == 'update-status':
        success = update_tenant_status(
            dynamodb_table_name=args.table,
            instance_id=args.instance_id,
            new_status=args.status
        )
        return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
