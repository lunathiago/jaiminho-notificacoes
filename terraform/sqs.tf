# SQS Queue Configuration for Message Buffering

# Dead Letter Queue (DLQ)
resource "aws_sqs_queue" "message_dlq" {
  name_prefix               = "${local.name_prefix}-message-dlq-"
  message_retention_seconds = var.sqs_message_retention_seconds
  
  # Enable encryption at rest
  sqs_managed_sse_enabled = true

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-message-dlq"
    Type = "DeadLetterQueue"
  })
}

# Main Message Queue
resource "aws_sqs_queue" "message_buffer" {
  name_prefix               = "${local.name_prefix}-message-buffer-"
  message_retention_seconds = var.sqs_message_retention_seconds
  visibility_timeout_seconds = var.sqs_visibility_timeout_seconds
  
  # Enable encryption at rest
  sqs_managed_sse_enabled = true

  # Configure Dead Letter Queue
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.message_dlq.arn
    maxReceiveCount     = 3
  })

  # Enable long polling to reduce costs
  receive_wait_time_seconds = 20

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-message-buffer"
    Type = "MessageBuffer"
  })
}

# SQS Queue Policy - Allow specific services to send messages
resource "aws_sqs_queue_policy" "message_buffer" {
  queue_url = aws_sqs_queue.message_buffer.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowLambdaSendMessage"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = [
          "sqs:SendMessage",
          "sqs:SendMessageBatch"
        ]
        Resource = aws_sqs_queue.message_buffer.arn
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = [
              aws_lambda_function.message_orchestrator.arn
            ]
          }
        }
      }
    ]
  })
}

# CloudWatch Alarms for SQS
resource "aws_cloudwatch_metric_alarm" "sqs_dlq_messages" {
  alarm_name          = "${local.name_prefix}-sqs-dlq-messages"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = "300"
  statistic           = "Average"
  threshold           = "10"
  alarm_description   = "Alert when messages are in DLQ"
  alarm_actions       = [] # Add SNS topic ARN for notifications

  dimensions = {
    QueueName = aws_sqs_queue.message_dlq.name
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "sqs_age_of_oldest_message" {
  alarm_name          = "${local.name_prefix}-sqs-message-age"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "ApproximateAgeOfOldestMessage"
  namespace           = "AWS/SQS"
  period              = "300"
  statistic           = "Maximum"
  threshold           = "3600" # 1 hour
  alarm_description   = "Alert when oldest message is too old"
  alarm_actions       = [] # Add SNS topic ARN for notifications

  dimensions = {
    QueueName = aws_sqs_queue.message_buffer.name
  }

  tags = local.common_tags
}

# Lambda Event Source Mapping for SQS
resource "aws_lambda_event_source_mapping" "sqs_to_orchestrator" {
  event_source_arn = aws_sqs_queue.message_buffer.arn
  function_name    = aws_lambda_function.message_orchestrator.arn
  batch_size       = 10
  
  # Enable function response types for partial batch failures
  function_response_types = ["ReportBatchItemFailures"]
  
  # Maximum batching window
  maximum_batching_window_in_seconds = 5

  # Scaling configuration
  scaling_config {
    maximum_concurrency = 10
  }

  depends_on = [
    aws_iam_role_policy_attachment.lambda_orchestrator_sqs
  ]
}
