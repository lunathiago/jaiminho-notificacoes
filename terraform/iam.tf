# IAM Roles and Policies with Least Privilege

# -----------------------------------------------------------------------------
# Message Orchestrator Lambda Role
# -----------------------------------------------------------------------------
resource "aws_iam_role" "lambda_orchestrator" {
  name_prefix = "${local.name_prefix}-lambda-orchestrator-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name     = "${local.name_prefix}-lambda-orchestrator-role"
    Function = "MessageOrchestrator"
  })
}

# Basic execution policy
resource "aws_iam_role_policy_attachment" "lambda_orchestrator_basic" {
  role       = aws_iam_role.lambda_orchestrator.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# SQS policy for orchestrator
resource "aws_iam_role_policy" "lambda_orchestrator_sqs" {
  name_prefix = "${local.name_prefix}-orchestrator-sqs-"
  role        = aws_iam_role.lambda_orchestrator.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = aws_sqs_queue.message_buffer.arn
      },
      {
        Effect = "Allow"
        Action = [
          "sqs:SendMessage"
        ]
        Resource = aws_sqs_queue.message_dlq.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_orchestrator_sqs" {
  role       = aws_iam_role.lambda_orchestrator.name
  policy_arn = aws_iam_policy.lambda_orchestrator_sqs.arn
}

# DynamoDB policy for orchestrator
resource "aws_iam_role_policy" "lambda_orchestrator_dynamodb" {
  name_prefix = "${local.name_prefix}-orchestrator-dynamodb-"
  role        = aws_iam_role.lambda_orchestrator.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          aws_dynamodb_table.messages.arn,
          "${aws_dynamodb_table.messages.arn}/index/*",
          aws_dynamodb_table.tenants.arn,
          "${aws_dynamodb_table.tenants.arn}/index/*"
        ]
        Condition = {
          "ForAllValues:StringEquals" = {
            "dynamodb:LeadingKeys" = ["$${aws:PrincipalTag/tenant_id}"]
          }
        }
      }
    ]
  })
}

# RDS access for orchestrator
resource "aws_iam_role_policy" "lambda_orchestrator_rds" {
  name_prefix = "${local.name_prefix}-orchestrator-rds-"
  role        = aws_iam_role.lambda_orchestrator.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "rds-db:connect"
        ]
        Resource = "arn:aws:rds-db:${var.aws_region}:*:dbuser:${aws_db_instance.main.resource_id}/jaiminho_app"
      }
    ]
  })
}

# Secrets Manager access
resource "aws_iam_role_policy" "lambda_orchestrator_secrets" {
  name_prefix = "${local.name_prefix}-orchestrator-secrets-"
  role        = aws_iam_role.lambda_orchestrator.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          aws_secretsmanager_secret.db_master_password.arn,
          aws_secretsmanager_secret.evolution_api.arn,
          aws_secretsmanager_secret.app_config.arn
        ]
      }
    ]
  })
}

# Policy for SQS integration
resource "aws_iam_policy" "lambda_orchestrator_sqs" {
  name_prefix = "${local.name_prefix}-orchestrator-sqs-"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = aws_sqs_queue.message_buffer.arn
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# Daily Digest Lambda Role
# -----------------------------------------------------------------------------
resource "aws_iam_role" "lambda_digest" {
  name_prefix = "${local.name_prefix}-lambda-digest-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name     = "${local.name_prefix}-lambda-digest-role"
    Function = "DailyDigest"
  })
}

resource "aws_iam_role_policy_attachment" "lambda_digest_basic" {
  role       = aws_iam_role.lambda_digest.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# DynamoDB access for digest
resource "aws_iam_role_policy" "lambda_digest_dynamodb" {
  name_prefix = "${local.name_prefix}-digest-dynamodb-"
  role        = aws_iam_role.lambda_digest.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:GetItem",
          "dynamodb:PutItem"
        ]
        Resource = [
          aws_dynamodb_table.messages.arn,
          "${aws_dynamodb_table.messages.arn}/index/*",
          aws_dynamodb_table.digests.arn,
          "${aws_dynamodb_table.digests.arn}/index/*",
          aws_dynamodb_table.tenants.arn
        ]
      }
    ]
  })
}

# RDS access for digest
resource "aws_iam_role_policy" "lambda_digest_rds" {
  name_prefix = "${local.name_prefix}-digest-rds-"
  role        = aws_iam_role.lambda_digest.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "rds-db:connect"
        ]
        Resource = "arn:aws:rds-db:${var.aws_region}:*:dbuser:${aws_db_instance.main.resource_id}/jaiminho_app"
      }
    ]
  })
}

# Secrets access for digest
resource "aws_iam_role_policy" "lambda_digest_secrets" {
  name_prefix = "${local.name_prefix}-digest-secrets-"
  role        = aws_iam_role.lambda_digest.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          aws_secretsmanager_secret.db_master_password.arn,
          aws_secretsmanager_secret.sendpulse.arn,
          aws_secretsmanager_secret.app_config.arn
        ]
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# Feedback Handler Lambda Role
# -----------------------------------------------------------------------------
resource "aws_iam_role" "lambda_feedback" {
  name_prefix = "${local.name_prefix}-lambda-feedback-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name     = "${local.name_prefix}-lambda-feedback-role"
    Function = "FeedbackHandler"
  })
}

resource "aws_iam_role_policy_attachment" "lambda_feedback_basic" {
  role       = aws_iam_role.lambda_feedback.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# DynamoDB access for feedback
resource "aws_iam_role_policy" "lambda_feedback_dynamodb" {
  name_prefix = "${local.name_prefix}-feedback-dynamodb-"
  role        = aws_iam_role.lambda_feedback.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query"
        ]
        Resource = [
          aws_dynamodb_table.messages.arn,
          "${aws_dynamodb_table.messages.arn}/index/*",
          aws_dynamodb_table.digests.arn,
          "${aws_dynamodb_table.digests.arn}/index/*"
        ]
      }
    ]
  })
}

# RDS access for feedback
resource "aws_iam_role_policy" "lambda_feedback_rds" {
  name_prefix = "${local.name_prefix}-feedback-rds-"
  role        = aws_iam_role.lambda_feedback.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "rds-db:connect"
        ]
        Resource = "arn:aws:rds-db:${var.aws_region}:*:dbuser:${aws_db_instance.main.resource_id}/jaiminho_app"
      }
    ]
  })
}

# Secrets access for feedback
resource "aws_iam_role_policy" "lambda_feedback_secrets" {
  name_prefix = "${local.name_prefix}-feedback-secrets-"
  role        = aws_iam_role.lambda_feedback.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          aws_secretsmanager_secret.db_master_password.arn,
          aws_secretsmanager_secret.app_config.arn,
          aws_secretsmanager_secret.webhook_auth.arn
        ]
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# API Gateway CloudWatch Logging Role
# -----------------------------------------------------------------------------
resource "aws_iam_role" "api_gateway_cloudwatch" {
  name_prefix = "${local.name_prefix}-apigw-cloudwatch-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "apigateway.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-apigw-cloudwatch-role"
  })
}

resource "aws_iam_role_policy_attachment" "api_gateway_cloudwatch" {
  role       = aws_iam_role.api_gateway_cloudwatch.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonAPIGatewayPushToCloudWatchLogs"
}

# -----------------------------------------------------------------------------
# EventBridge Role for invoking Lambda
# -----------------------------------------------------------------------------
resource "aws_iam_role" "eventbridge_lambda" {
  name_prefix = "${local.name_prefix}-eventbridge-lambda-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "events.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-eventbridge-lambda-role"
  })
}

resource "aws_iam_role_policy" "eventbridge_lambda" {
  name_prefix = "${local.name_prefix}-eventbridge-lambda-"
  role        = aws_iam_role.eventbridge_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = aws_lambda_function.daily_digest.arn
      }
    ]
  })
}

