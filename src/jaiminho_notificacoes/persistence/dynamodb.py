"""DynamoDB repositories with strict tenant isolation."""

import os
from datetime import datetime
from typing import List, Optional

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from ..core.logger import get_logger
from .models import WAPIInstance

logger = get_logger(__name__)


def _iso(dt: datetime) -> str:
	"""Return an ISO 8601 string with UTC assumption."""
	return dt.replace(tzinfo=None).isoformat()


class WAPIInstanceRepository:
	"""Manage user-scoped W-API instances in DynamoDB."""

	def __init__(self, table_name: Optional[str] = None):
		self.table_name = table_name or os.getenv("DYNAMODB_WAPI_INSTANCES_TABLE")
		if not self.table_name:
			raise ValueError("DYNAMODB_WAPI_INSTANCES_TABLE environment variable not set")

		self.instance_lookup_index = os.getenv("DYNAMODB_WAPI_INSTANCE_GSI", "InstanceLookupIndex")
		self.dynamodb = boto3.resource("dynamodb")
		self.table = self.dynamodb.Table(self.table_name)

	@staticmethod
	def _serialize(instance: WAPIInstance) -> dict:
		"""Convert dataclass to a DynamoDB-compatible dictionary."""
		return {
			"tenant_id": instance.tenant_id,
			"user_id": instance.user_id,
			"wapi_instance_id": instance.wapi_instance_id,
			"instance_name": instance.instance_name,
			"phone_number": instance.phone_number,
			"status": instance.status,
			"api_key_hash": instance.api_key_hash,
			"created_at": _iso(instance.created_at),
			"updated_at": _iso(instance.updated_at),
			"metadata": instance.metadata or {},
		}

	@staticmethod
	def _deserialize(item: dict) -> WAPIInstance:
		"""Convert DynamoDB item to dataclass."""
		return WAPIInstance(
			tenant_id=item["tenant_id"],
			user_id=item["user_id"],
			wapi_instance_id=item["wapi_instance_id"],
			instance_name=item.get("instance_name", ""),
			phone_number=item.get("phone_number", ""),
			status=item.get("status", "unknown"),
			api_key_hash=item.get("api_key_hash", ""),
			created_at=datetime.fromisoformat(item["created_at"]),
			updated_at=datetime.fromisoformat(item["updated_at"]),
			metadata=item.get("metadata", {}),
		)

	def _query_instance_lookup(self, wapi_instance_id: str) -> Optional[WAPIInstance]:
		"""Query by instance id through the dedicated GSI."""
		try:
			response = self.table.query(
				IndexName=self.instance_lookup_index,
				KeyConditionExpression=Key("wapi_instance_id").eq(wapi_instance_id),
				Limit=1,
			)
		except ClientError as exc:
			logger.error(
				"Failed to query instance lookup index",
				instance_id=wapi_instance_id,
				details={"error": str(exc)},
			)
			return None

		items = response.get("Items", [])
		if not items:
			return None
		return self._deserialize(items[0])

	def get_by_instance_id(self, wapi_instance_id: str) -> Optional[WAPIInstance]:
		"""Fetch instance ownership by instance id (used during webhook resolution)."""
		return self._query_instance_lookup(wapi_instance_id)

	def get_for_user(self, user_id: str, wapi_instance_id: str) -> Optional[WAPIInstance]:
		"""Fetch instance scoped to a user to prevent cross-tenant reads."""
		try:
			response = self.table.get_item(
				Key={"user_id": user_id, "wapi_instance_id": wapi_instance_id}
			)
		except ClientError as exc:
			logger.error(
				"Failed to read instance for user",
				user_id=user_id,
				instance_id=wapi_instance_id,
				details={"error": str(exc)},
			)
			return None

		item = response.get("Item")
		return self._deserialize(item) if item else None

	def list_for_user(self, user_id: str) -> List[WAPIInstance]:
		"""List all instances for a user; always scoped by user_id."""
		try:
			response = self.table.query(
				KeyConditionExpression=Key("user_id").eq(user_id)
			)
		except ClientError as exc:
			logger.error(
				"Failed to list instances for user",
				user_id=user_id,
				details={"error": str(exc)},
			)
			return []

		return [self._deserialize(item) for item in response.get("Items", [])]

	def create_instance(self, instance: WAPIInstance) -> bool:
		"""Create a new instance mapping ensuring one-to-one ownership."""
		existing = self.get_by_instance_id(instance.wapi_instance_id)
		if existing:
			if existing.user_id != instance.user_id:
				raise ValueError("wapi_instance_id already assigned to a different user")
			if existing.tenant_id != instance.tenant_id:
				raise ValueError("wapi_instance_id already bound to a different tenant")

		now = datetime.utcnow()
		instance.created_at = instance.created_at or now
		instance.updated_at = now

		try:
			self.table.put_item(
				Item=self._serialize(instance),
				ConditionExpression="attribute_not_exists(user_id) AND attribute_not_exists(wapi_instance_id)",
			)
			return True
		except ClientError as exc:
			if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
				logger.warning(
					"Instance already exists for user",
					user_id=instance.user_id,
					instance_id=instance.wapi_instance_id,
				)
			else:
				logger.error(
					"Failed to create wapi instance",
					user_id=instance.user_id,
					instance_id=instance.wapi_instance_id,
					details={"error": str(exc)},
				)
			return False

	def update_status(self, user_id: str, wapi_instance_id: str, status: str) -> bool:
		"""Update status while asserting ownership to avoid cross-tenant changes."""
		try:
			self.table.update_item(
				Key={"user_id": user_id, "wapi_instance_id": wapi_instance_id},
				ConditionExpression="attribute_exists(user_id) AND attribute_exists(wapi_instance_id)",
				UpdateExpression="SET #s = :status, updated_at = :updated_at",
				ExpressionAttributeNames={"#s": "status"},
				ExpressionAttributeValues={
					":status": status,
					":updated_at": _iso(datetime.utcnow()),
				},
			)
			return True
		except ClientError as exc:
			logger.error(
				"Failed to update instance status",
				user_id=user_id,
				instance_id=wapi_instance_id,
				details={"error": str(exc)},
			)
			return False

	def delete_instance(self, user_id: str, wapi_instance_id: str) -> bool:
		"""Delete an instance, scoped by user_id to prevent cross-tenant deletion."""
		try:
			self.table.delete_item(
				Key={"user_id": user_id, "wapi_instance_id": wapi_instance_id},
				ConditionExpression="attribute_exists(user_id) AND attribute_exists(wapi_instance_id)",
			)
			return True
		except ClientError as exc:
			logger.error(
				"Failed to delete instance",
				user_id=user_id,
				instance_id=wapi_instance_id,
				details={"error": str(exc)},
			)
			return False
