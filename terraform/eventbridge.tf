# EventBridge Configuration for Daily Digest Scheduling

# EventBridge Rule for Daily Digest
resource "aws_cloudwatch_event_rule" "daily_digest" {
  name                = "${local.name_prefix}-daily-digest"
  description         = "Trigger daily digest generation"
  schedule_expression = var.daily_digest_schedule
  state               = "ENABLED"

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-daily-digest-rule"
  })
}

# EventBridge Target - Lambda Function
resource "aws_cloudwatch_event_target" "daily_digest" {
  rule      = aws_cloudwatch_event_rule.daily_digest.name
  target_id = "DailyDigestLambda"
  arn       = aws_lambda_function.daily_digest.arn
  role_arn  = aws_iam_role.eventbridge_lambda.arn

  # Retry policy
  retry_policy {
    maximum_retry_attempts  = 2
  }

  # Dead letter queue for failed invocations
  dead_letter_config {
    arn = aws_sqs_queue.eventbridge_dlq.arn
  }

  # Input transformation to add context
  input_transformer {
    input_paths = {
      time = "$.time"
    }
    input_template = <<EOF
{
  "trigger": "scheduled",
  "scheduled_time": <time>,
  "environment": "${var.environment}"
}
EOF
  }
}

# DLQ for EventBridge failures
resource "aws_sqs_queue" "eventbridge_dlq" {
  name_prefix               = "${local.name_prefix}-eventbridge-dlq-"
  message_retention_seconds = var.sqs_message_retention_seconds
  sqs_managed_sse_enabled   = true

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-eventbridge-dlq"
    Type = "EventBridgeDLQ"
  })
}

# CloudWatch Alarm for EventBridge DLQ
resource "aws_cloudwatch_metric_alarm" "eventbridge_dlq" {
  alarm_name          = "${local.name_prefix}-eventbridge-dlq-messages"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = "300"
  statistic           = "Average"
  threshold           = "1"
  alarm_description   = "Alert when EventBridge has failed invocations"
  alarm_actions       = [] # Add SNS topic ARN

  dimensions = {
    QueueName = aws_sqs_queue.eventbridge_dlq.name
  }

  tags = local.common_tags
}

# Optional: EventBridge Rule for urgent message processing
resource "aws_cloudwatch_event_rule" "urgent_messages" {
  name          = "${local.name_prefix}-urgent-messages"
  description   = "Trigger immediate processing for urgent messages"
  event_pattern = jsonencode({
    source      = ["jaiminho.messages"]
    detail-type = ["Message Received"]
    detail = {
      urgency = ["high", "critical"]
    }
  })
  state = "ENABLED"

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-urgent-messages-rule"
  })
}

resource "aws_cloudwatch_event_target" "urgent_messages" {
  rule      = aws_cloudwatch_event_rule.urgent_messages.name
  target_id = "UrgentMessageOrchestrator"
  arn       = aws_lambda_function.message_orchestrator.arn
  role_arn  = aws_iam_role.eventbridge_lambda.arn

  retry_policy {
    maximum_retry_attempts = 3
  }
}

# Lambda permission for urgent messages EventBridge rule
resource "aws_lambda_permission" "eventbridge_urgent" {
  statement_id  = "AllowEventBridgeUrgentInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.message_orchestrator.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.urgent_messages.arn
}

# EventBridge Bus for custom events (optional)
resource "aws_cloudwatch_event_bus" "jaiminho" {
  name = "${local.name_prefix}-events"

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-event-bus"
  })

  lifecycle {
    ignore_changes = all
  }
}

# Archive for event replay (production only)
resource "aws_cloudwatch_event_archive" "main" {
  count            = var.environment == "prod" ? 1 : 0
  name             = "${local.name_prefix}-archive"
  event_source_arn = aws_cloudwatch_event_bus.jaiminho.arn
  retention_days   = 90

  description = "Event archive for replay and audit"
}

# IAM policy for EventBridge to send to DLQ
resource "aws_sqs_queue_policy" "eventbridge_dlq" {
  queue_url = aws_sqs_queue.eventbridge_dlq.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowEventBridgeSendMessage"
        Effect = "Allow"
        Principal = {
          Service = "events.amazonaws.com"
        }
        Action = [
          "sqs:SendMessage"
        ]
        Resource = aws_sqs_queue.eventbridge_dlq.arn
      }
    ]
  })
}
