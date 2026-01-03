# DynamoDB Tables for Multi-Tenant Data Storage

# Messages Table - stores all WhatsApp messages with tenant isolation
resource "aws_dynamodb_table" "messages" {
  name           = "${local.name_prefix}-messages"
  billing_mode   = "PAY_PER_REQUEST" # On-demand pricing for variable workloads
  hash_key       = "tenant_id"
  range_key      = "message_id"

  attribute {
    name = "tenant_id"
    type = "S"
  }

  attribute {
    name = "message_id"
    type = "S"
  }

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "N"
  }

  attribute {
    name = "status"
    type = "S"
  }

  # Global Secondary Index for user-based queries
  global_secondary_index {
    name            = "UserIndex"
    hash_key        = "tenant_id"
    range_key       = "user_id"
    projection_type = "ALL"
  }

  # Global Secondary Index for timestamp-based queries
  global_secondary_index {
    name            = "TimestampIndex"
    hash_key        = "tenant_id"
    range_key       = "timestamp"
    projection_type = "ALL"
  }

  # Global Secondary Index for status-based queries
  global_secondary_index {
    name            = "StatusIndex"
    hash_key        = "tenant_id"
    range_key       = "status"
    projection_type = "ALL"
  }

  # Enable point-in-time recovery
  point_in_time_recovery {
    enabled = var.environment == "prod"
  }

  # Enable encryption at rest
  server_side_encryption {
    enabled = true
  }

  # Enable TTL for automatic data cleanup
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-messages"
  })
}

# Digest History Table - stores generated digests
resource "aws_dynamodb_table" "digests" {
  name           = "${local.name_prefix}-digests"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "tenant_id"
  range_key      = "digest_id"

  attribute {
    name = "tenant_id"
    type = "S"
  }

  attribute {
    name = "digest_id"
    type = "S"
  }

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "N"
  }

  # Global Secondary Index for user-based digest queries
  global_secondary_index {
    name            = "UserDigestIndex"
    hash_key        = "tenant_id"
    range_key       = "user_id"
    projection_type = "ALL"
  }

  # Global Secondary Index for date-based digest queries
  global_secondary_index {
    name            = "DateIndex"
    hash_key        = "tenant_id"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = var.environment == "prod"
  }

  server_side_encryption {
    enabled = true
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-digests"
  })
}

# Tenant Configuration Table - stores tenant-specific settings
resource "aws_dynamodb_table" "tenants" {
  name           = "${local.name_prefix}-tenants"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "tenant_id"

  attribute {
    name = "tenant_id"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  # Global Secondary Index for status-based queries
  global_secondary_index {
    name            = "StatusIndex"
    hash_key        = "status"
    range_key       = "tenant_id"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = var.environment == "prod"
  }

  server_side_encryption {
    enabled = true
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-tenants"
  })
}

# W-API Instances Table - enforces one-to-one mapping between instances and users
resource "aws_dynamodb_table" "wapi_instances" {
  name         = "${local.name_prefix}-wapi-instances"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  range_key    = "wapi_instance_id"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "wapi_instance_id"
    type = "S"
  }

  attribute {
    name = "tenant_id"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  global_secondary_index {
    name            = "InstanceLookupIndex"
    hash_key        = "wapi_instance_id"
    range_key       = "user_id"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = var.environment == "prod"
  }

  server_side_encryption {
    enabled = true
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-wapi-instances"
  })
}

# User Feedback Table - stores binary feedback on message urgency
resource "aws_dynamodb_table" "feedback" {
  name           = "${local.name_prefix}-feedback"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "PK"
  range_key      = "SK"

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  attribute {
    name = "tenant_id"
    type = "S"
  }

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "sender_phone"
    type = "S"
  }

  # GSI for querying feedback by tenant and user
  global_secondary_index {
    name            = "TenantUserIndex"
    hash_key        = "tenant_id"
    range_key       = "user_id"
    projection_type = "ALL"
  }

  # GSI for querying feedback by sender
  global_secondary_index {
    name            = "SenderIndex"
    hash_key        = "user_id"
    range_key       = "sender_phone"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = var.environment == "prod"
  }

  server_side_encryption {
    enabled = true
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-feedback"
  })
}

# Interruption Statistics Table - aggregated statistics per sender/category/user
resource "aws_dynamodb_table" "interruption_stats" {
  name           = "${local.name_prefix}-interruption-stats"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "PK"
  range_key      = "SK"

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  attribute {
    name = "tenant_id"
    type = "S"
  }

  attribute {
    name = "user_id"
    type = "S"
  }

  # GSI for querying stats by tenant and user
  global_secondary_index {
    name            = "TenantUserIndex"
    hash_key        = "tenant_id"
    range_key       = "user_id"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = var.environment == "prod"
  }

  server_side_encryption {
    enabled = true
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-interruption-stats"
  })
}

# CloudWatch Alarms for DynamoDB
resource "aws_cloudwatch_metric_alarm" "dynamodb_user_errors" {
  alarm_name          = "${local.name_prefix}-dynamodb-user-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "UserErrors"
  namespace           = "AWS/DynamoDB"
  period              = "300"
  statistic           = "Sum"
  threshold           = "10"
  alarm_description   = "Alert on DynamoDB user errors"
  alarm_actions       = [] # Add SNS topic ARN for notifications

  dimensions = {
    TableName = aws_dynamodb_table.messages.name
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "dynamodb_throttled_requests" {
  alarm_name          = "${local.name_prefix}-dynamodb-throttled"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "UserErrors"
  namespace           = "AWS/DynamoDB"
  period              = "300"
  statistic           = "Sum"
  threshold           = "5"
  alarm_description   = "Alert on DynamoDB throttled requests"
  alarm_actions       = [] # Add SNS topic ARN for notifications

  dimensions = {
    TableName = aws_dynamodb_table.messages.name
  }

  tags = local.common_tags
}

