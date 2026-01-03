# AWS Lambda Functions Configuration

# Create placeholder Lambda deployment package
data "archive_file" "lambda_placeholder" {
  type        = "zip"
  output_path = "${path.module}/lambda_placeholder.zip"

  source {
    content  = "def handler(event, context): return {'statusCode': 200}"
    filename = "index.py"
  }
}

# -----------------------------------------------------------------------------
# Message Orchestrator Lambda
# -----------------------------------------------------------------------------
resource "aws_lambda_function" "message_orchestrator" {
  function_name = "${local.name_prefix}-message-orchestrator"
  description   = "Processes incoming WhatsApp messages and routes based on urgency"
  
  filename         = data.archive_file.lambda_placeholder.output_path
  source_code_hash = data.archive_file.lambda_placeholder.output_base64sha256
  
  role    = aws_iam_role.lambda_orchestrator.arn
  handler = "lambda_handlers.process_messages.handler"
  runtime = var.lambda_runtime
  
  memory_size = var.lambda_memory_size
  timeout     = var.lambda_timeout

  # VPC Configuration for RDS access
  vpc_config {
    subnet_ids         = aws_subnet.private[*].id
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = {
      ENVIRONMENT            = var.environment
      DB_SECRET_ARN          = aws_secretsmanager_secret.db_master_password.arn
      WAPI_SECRET   = aws_secretsmanager_secret.wapi.arn
      APP_CONFIG_SECRET      = aws_secretsmanager_secret.app_config.arn
      SQS_QUEUE_URL          = aws_sqs_queue.message_buffer.url
      DYNAMODB_MESSAGES_TABLE = aws_dynamodb_table.messages.name
      DYNAMODB_TENANTS_TABLE  = aws_dynamodb_table.tenants.name
      AWS_REGION             = var.aws_region
      LOG_LEVEL              = var.environment == "prod" ? "INFO" : "DEBUG"
    }
  }

  # Reserved concurrent executions to prevent runaway costs
  reserved_concurrent_executions = var.environment == "prod" ? 50 : 10

  # X-Ray tracing for observability
  tracing_config {
    mode = "Active"
  }

  tags = merge(local.common_tags, {
    Name     = "${local.name_prefix}-message-orchestrator"
    Function = "MessageProcessing"
  })

  lifecycle {
    ignore_changes = [
      filename,
      source_code_hash,
      last_modified
    ]
  }

  depends_on = [
    aws_iam_role_policy.lambda_orchestrator_dynamodb,
    aws_iam_role_policy.lambda_orchestrator_rds,
    aws_iam_role_policy.lambda_orchestrator_secrets,
    aws_cloudwatch_log_group.lambda_orchestrator
  ]
}

# CloudWatch Log Group for orchestrator
resource "aws_cloudwatch_log_group" "lambda_orchestrator" {
  name              = "/aws/lambda/${local.name_prefix}-message-orchestrator"
  retention_in_days = var.environment == "prod" ? 30 : 7

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-orchestrator-logs"
  })
}

# CloudWatch Alarms for orchestrator
resource "aws_cloudwatch_metric_alarm" "lambda_orchestrator_errors" {
  alarm_name          = "${local.name_prefix}-orchestrator-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = "300"
  statistic           = "Sum"
  threshold           = "10"
  alarm_description   = "Alert when orchestrator has high error rate"
  alarm_actions       = [] # Add SNS topic ARN

  dimensions = {
    FunctionName = aws_lambda_function.message_orchestrator.function_name
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "lambda_orchestrator_duration" {
  alarm_name          = "${local.name_prefix}-orchestrator-duration"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = "300"
  statistic           = "Average"
  threshold           = "50000" # 50 seconds
  alarm_description   = "Alert when orchestrator is slow"
  alarm_actions       = [] # Add SNS topic ARN

  dimensions = {
    FunctionName = aws_lambda_function.message_orchestrator.function_name
  }

  tags = local.common_tags
}

# -----------------------------------------------------------------------------
# Daily Digest Lambda
# -----------------------------------------------------------------------------
resource "aws_lambda_function" "daily_digest" {
  function_name = "${local.name_prefix}-daily-digest"
  description   = "Generates and sends daily digest emails"
  
  filename         = data.archive_file.lambda_placeholder.output_path
  source_code_hash = data.archive_file.lambda_placeholder.output_base64sha256
  
  role    = aws_iam_role.lambda_digest.arn
  handler = "lambda_handlers.generate_digest.handler"
  runtime = var.lambda_runtime
  
  memory_size = 1024 # Higher memory for digest generation
  timeout     = 300  # 5 minutes for batch processing

  vpc_config {
    subnet_ids         = aws_subnet.private[*].id
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = {
      ENVIRONMENT              = var.environment
      DB_SECRET_ARN            = aws_secretsmanager_secret.db_master_password.arn
      SENDPULSE_SECRET         = aws_secretsmanager_secret.sendpulse.arn
      APP_CONFIG_SECRET        = aws_secretsmanager_secret.app_config.arn
      DYNAMODB_MESSAGES_TABLE  = aws_dynamodb_table.messages.name
      DYNAMODB_DIGESTS_TABLE   = aws_dynamodb_table.digests.name
      DYNAMODB_TENANTS_TABLE   = aws_dynamodb_table.tenants.name
      AWS_REGION               = var.aws_region
      LOG_LEVEL                = var.environment == "prod" ? "INFO" : "DEBUG"
    }
  }

  reserved_concurrent_executions = var.environment == "prod" ? 10 : 2

  tracing_config {
    mode = "Active"
  }

  tags = merge(local.common_tags, {
    Name     = "${local.name_prefix}-daily-digest"
    Function = "DigestGeneration"
  })

  lifecycle {
    ignore_changes = [
      filename,
      source_code_hash,
      last_modified
    ]
  }

  depends_on = [
    aws_iam_role_policy.lambda_digest_dynamodb,
    aws_iam_role_policy.lambda_digest_rds,
    aws_iam_role_policy.lambda_digest_secrets,
    aws_cloudwatch_log_group.lambda_digest
  ]
}

resource "aws_cloudwatch_log_group" "lambda_digest" {
  name              = "/aws/lambda/${local.name_prefix}-daily-digest"
  retention_in_days = var.environment == "prod" ? 30 : 7

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-digest-logs"
  })
}

resource "aws_cloudwatch_metric_alarm" "lambda_digest_errors" {
  alarm_name          = "${local.name_prefix}-digest-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = "300"
  statistic           = "Sum"
  threshold           = "1"
  alarm_description   = "Alert when digest generation fails"
  alarm_actions       = [] # Add SNS topic ARN

  dimensions = {
    FunctionName = aws_lambda_function.daily_digest.function_name
  }

  tags = local.common_tags
}

# -----------------------------------------------------------------------------
# Feedback Handler Lambda
# -----------------------------------------------------------------------------
resource "aws_lambda_function" "feedback_handler" {
  function_name = "${local.name_prefix}-feedback-handler"
  description   = "Handles user feedback on notifications and digests"
  
  filename         = data.archive_file.lambda_placeholder.output_path
  source_code_hash = data.archive_file.lambda_placeholder.output_base64sha256
  
  role    = aws_iam_role.lambda_feedback.arn
  handler = "lambda_handlers.send_notifications.handler"
  runtime = var.lambda_runtime
  
  memory_size = var.lambda_memory_size
  timeout     = var.lambda_timeout

  vpc_config {
    subnet_ids         = aws_subnet.private[*].id
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = {
      ENVIRONMENT              = var.environment
      DB_SECRET_ARN            = aws_secretsmanager_secret.db_master_password.arn
      APP_CONFIG_SECRET        = aws_secretsmanager_secret.app_config.arn
      WEBHOOK_AUTH_SECRET      = aws_secretsmanager_secret.webhook_auth.arn
      DYNAMODB_MESSAGES_TABLE  = aws_dynamodb_table.messages.name
      DYNAMODB_DIGESTS_TABLE   = aws_dynamodb_table.digests.name
      AWS_REGION               = var.aws_region
      LOG_LEVEL                = var.environment == "prod" ? "INFO" : "DEBUG"
    }
  }

  reserved_concurrent_executions = var.environment == "prod" ? 20 : 5

  tracing_config {
    mode = "Active"
  }

  tags = merge(local.common_tags, {
    Name     = "${local.name_prefix}-feedback-handler"
    Function = "FeedbackProcessing"
  })

  lifecycle {
    ignore_changes = [
      filename,
      source_code_hash,
      last_modified
    ]
  }

  depends_on = [
    aws_iam_role_policy.lambda_feedback_dynamodb,
    aws_iam_role_policy.lambda_feedback_rds,
    aws_iam_role_policy.lambda_feedback_secrets,
    aws_cloudwatch_log_group.lambda_feedback
  ]
}

resource "aws_cloudwatch_log_group" "lambda_feedback" {
  name              = "/aws/lambda/${local.name_prefix}-feedback-handler"
  retention_in_days = var.environment == "prod" ? 30 : 7

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-feedback-logs"
  })
}

# Lambda permissions for API Gateway
resource "aws_lambda_permission" "api_gateway_orchestrator" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.message_orchestrator.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

resource "aws_lambda_permission" "api_gateway_feedback" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.feedback_handler.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

# Lambda permission for EventBridge
resource "aws_lambda_permission" "eventbridge_digest" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.daily_digest.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_digest.arn
}

# Lambda Function URL for feedback (optional alternative to API Gateway)
resource "aws_lambda_function_url" "feedback" {
  function_name      = aws_lambda_function.feedback_handler.function_name
  authorization_type = "NONE" # Use custom authorization in Lambda code

  cors {
    allow_credentials = false
    allow_origins     = ["*"]
    allow_methods     = ["POST"]
    max_age           = 86400
  }
}

