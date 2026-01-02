# AWS Secrets Manager Configuration

# Evolution API Credentials
resource "aws_secretsmanager_secret" "evolution_api" {
  name_prefix             = "${local.name_prefix}-evolution-api-"
  description             = "Evolution API credentials and configuration"
  recovery_window_in_days = var.environment == "prod" ? 30 : 0

  tags = merge(local.common_tags, {
    Name        = "${local.name_prefix}-evolution-api"
    ServiceType = "ExternalAPI"
  })
}

resource "aws_secretsmanager_secret_version" "evolution_api_placeholder" {
  secret_id = aws_secretsmanager_secret.evolution_api.id
  secret_string = jsonencode({
    api_key     = "PLACEHOLDER_UPDATE_AFTER_DEPLOYMENT"
    api_url     = "https://api.evolution.example.com"
    instance_id = "PLACEHOLDER_INSTANCE_ID"
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# SendPulse API Credentials
resource "aws_secretsmanager_secret" "sendpulse" {
  name_prefix             = "${local.name_prefix}-sendpulse-"
  description             = "SendPulse API credentials"
  recovery_window_in_days = var.environment == "prod" ? 30 : 0

  tags = merge(local.common_tags, {
    Name        = "${local.name_prefix}-sendpulse"
    ServiceType = "ExternalAPI"
  })
}

resource "aws_secretsmanager_secret_version" "sendpulse_placeholder" {
  secret_id = aws_secretsmanager_secret.sendpulse.id
  secret_string = jsonencode({
    client_id     = "PLACEHOLDER_UPDATE_AFTER_DEPLOYMENT"
    client_secret = "PLACEHOLDER_UPDATE_AFTER_DEPLOYMENT"
    api_url       = "https://api.sendpulse.com"
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# Application Configuration Secret
resource "aws_secretsmanager_secret" "app_config" {
  name_prefix             = "${local.name_prefix}-app-config-"
  description             = "Application configuration and encryption keys"
  recovery_window_in_days = var.environment == "prod" ? 30 : 0

  tags = merge(local.common_tags, {
    Name        = "${local.name_prefix}-app-config"
    ServiceType = "Application"
  })
}

# Generate encryption key for application
resource "random_password" "app_encryption_key" {
  length  = 64
  special = true
}

resource "aws_secretsmanager_secret_version" "app_config" {
  secret_id = aws_secretsmanager_secret.app_config.id
  secret_string = jsonencode({
    encryption_key = random_password.app_encryption_key.result
    jwt_secret     = random_password.app_encryption_key.result
    environment    = var.environment
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# Webhook Authentication Secret
resource "aws_secretsmanager_secret" "webhook_auth" {
  name_prefix             = "${local.name_prefix}-webhook-auth-"
  description             = "Webhook authentication tokens"
  recovery_window_in_days = var.environment == "prod" ? 30 : 0

  tags = merge(local.common_tags, {
    Name        = "${local.name_prefix}-webhook-auth"
    ServiceType = "Authentication"
  })
}

resource "random_password" "webhook_token" {
  length  = 32
  special = false
}

resource "aws_secretsmanager_secret_version" "webhook_auth" {
  secret_id = aws_secretsmanager_secret.webhook_auth.id
  secret_string = jsonencode({
    webhook_token = random_password.webhook_token.result
    api_key       = random_password.webhook_token.result
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# Secret Rotation Configuration (for production)
resource "aws_secretsmanager_secret_rotation" "evolution_api" {
  count               = var.environment == "prod" ? 1 : 0
  secret_id           = aws_secretsmanager_secret.evolution_api.id
  rotation_lambda_arn = aws_lambda_function.secret_rotation[0].arn

  rotation_rules {
    automatically_after_days = 90
  }

  depends_on = [aws_lambda_permission.secret_rotation]
}

# Lambda for Secret Rotation (production only)
resource "aws_lambda_function" "secret_rotation" {
  count         = var.environment == "prod" ? 1 : 0
  filename      = "lambda_placeholder.zip"
  function_name = "${local.name_prefix}-secret-rotation"
  role          = aws_iam_role.secret_rotation[0].arn
  handler       = "index.handler"
  runtime       = var.lambda_runtime
  timeout       = 30

  environment {
    variables = {
      ENVIRONMENT = var.environment
    }
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-secret-rotation"
  })

  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }
}

# IAM Role for Secret Rotation Lambda
resource "aws_iam_role" "secret_rotation" {
  count       = var.environment == "prod" ? 1 : 0
  name_prefix = "${local.name_prefix}-secret-rotation-"

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
    Name = "${local.name_prefix}-secret-rotation-role"
  })
}

# Permission for Secrets Manager to invoke rotation Lambda
resource "aws_lambda_permission" "secret_rotation" {
  count         = var.environment == "prod" ? 1 : 0
  statement_id  = "AllowExecutionFromSecretsManager"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.secret_rotation[0].function_name
  principal     = "secretsmanager.amazonaws.com"
}

# Output secret ARNs for Lambda environment variables
output "secret_arns" {
  description = "ARNs of secrets for Lambda configuration"
  value = {
    evolution_api = aws_secretsmanager_secret.evolution_api.arn
    sendpulse     = aws_secretsmanager_secret.sendpulse.arn
    app_config    = aws_secretsmanager_secret.app_config.arn
    webhook_auth  = aws_secretsmanager_secret.webhook_auth.arn
    db_master     = aws_secretsmanager_secret.db_master_password.arn
  }
  sensitive = true
}
