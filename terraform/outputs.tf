# Terraform Outputs

# API Gateway
output "api_gateway_url" {
  description = "URL do API Gateway"
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "api_gateway_id" {
  description = "ID do API Gateway"
  value       = aws_apigatewayv2_api.main.id
}

output "webhook_endpoint" {
  description = "Endpoint completo para webhooks"
  value       = "${aws_apigatewayv2_stage.default.invoke_url}/webhook"
}

output "feedback_endpoint" {
  description = "Endpoint completo para feedback"
  value       = "${aws_apigatewayv2_stage.default.invoke_url}/feedback"
}

# Lambda Functions
output "lambda_orchestrator_arn" {
  description = "ARN da Lambda de orquestração"
  value       = aws_lambda_function.message_orchestrator.arn
}

output "lambda_orchestrator_name" {
  description = "Nome da Lambda de orquestração"
  value       = aws_lambda_function.message_orchestrator.function_name
}

output "lambda_digest_arn" {
  description = "ARN da Lambda de digest"
  value       = aws_lambda_function.daily_digest.arn
}

output "lambda_digest_name" {
  description = "Nome da Lambda de digest"
  value       = aws_lambda_function.daily_digest.function_name
}

output "lambda_feedback_arn" {
  description = "ARN da Lambda de feedback"
  value       = aws_lambda_function.feedback_handler.arn
}

output "lambda_feedback_name" {
  description = "Nome da Lambda de feedback"
  value       = aws_lambda_function.feedback_handler.function_name
}

output "lambda_feedback_url" {
  description = "URL pública da Lambda de feedback"
  value       = aws_lambda_function_url.feedback.function_url
}

# RDS
output "rds_endpoint" {
  description = "Endpoint do RDS PostgreSQL"
  value       = aws_db_instance.main.endpoint
  sensitive   = true
}

output "rds_address" {
  description = "Endereço do RDS PostgreSQL"
  value       = aws_db_instance.main.address
  sensitive   = true
}

output "rds_port" {
  description = "Porta do RDS PostgreSQL"
  value       = aws_db_instance.main.port
}

output "rds_database_name" {
  description = "Nome do banco de dados"
  value       = aws_db_instance.main.db_name
}

# SQS
output "sqs_queue_url" {
  description = "URL da fila SQS principal"
  value       = aws_sqs_queue.message_buffer.url
}

output "sqs_queue_arn" {
  description = "ARN da fila SQS principal"
  value       = aws_sqs_queue.message_buffer.arn
}

output "sqs_dlq_url" {
  description = "URL da DLQ"
  value       = aws_sqs_queue.message_dlq.url
}

output "sqs_dlq_arn" {
  description = "ARN da DLQ"
  value       = aws_sqs_queue.message_dlq.arn
}

# DynamoDB
output "dynamodb_messages_table" {
  description = "Nome da tabela DynamoDB de mensagens"
  value       = aws_dynamodb_table.messages.name
}

output "dynamodb_messages_arn" {
  description = "ARN da tabela DynamoDB de mensagens"
  value       = aws_dynamodb_table.messages.arn
}

output "dynamodb_digests_table" {
  description = "Nome da tabela DynamoDB de digests"
  value       = aws_dynamodb_table.digests.name
}

output "dynamodb_tenants_table" {
  description = "Nome da tabela DynamoDB de tenants"
  value       = aws_dynamodb_table.tenants.name
}

# Secrets Manager
output "secret_db_master_arn" {
  description = "ARN do secret com credenciais do RDS"
  value       = aws_secretsmanager_secret.db_master_password.arn
  sensitive   = true
}

output "secret_evolution_api_arn" {
  description = "ARN do secret da Evolution API"
  value       = aws_secretsmanager_secret.evolution_api.arn
  sensitive   = true
}

output "secret_sendpulse_arn" {
  description = "ARN do secret do SendPulse"
  value       = aws_secretsmanager_secret.sendpulse.arn
  sensitive   = true
}

output "secret_app_config_arn" {
  description = "ARN do secret de configuração da aplicação"
  value       = aws_secretsmanager_secret.app_config.arn
  sensitive   = true
}

output "secret_webhook_auth_arn" {
  description = "ARN do secret de autenticação de webhooks"
  value       = aws_secretsmanager_secret.webhook_auth.arn
  sensitive   = true
}

# EventBridge
output "eventbridge_rule_daily_digest" {
  description = "Nome da regra EventBridge para digest diário"
  value       = aws_cloudwatch_event_rule.daily_digest.name
}

output "eventbridge_bus_arn" {
  description = "ARN do EventBridge custom bus"
  value       = aws_cloudwatch_event_bus.jaiminho.arn
}

# VPC
output "vpc_id" {
  description = "ID da VPC"
  value       = aws_vpc.main.id
}

output "private_subnet_ids" {
  description = "IDs das subnets privadas"
  value       = aws_subnet.private[*].id
}

output "public_subnet_ids" {
  description = "IDs das subnets públicas"
  value       = aws_subnet.public[*].id
}

output "lambda_security_group_id" {
  description = "ID do security group das Lambdas"
  value       = aws_security_group.lambda.id
}

output "rds_security_group_id" {
  description = "ID do security group do RDS"
  value       = aws_security_group.rds.id
}

# CloudWatch Log Groups
output "log_group_orchestrator" {
  description = "Nome do log group da Lambda orchestrator"
  value       = aws_cloudwatch_log_group.lambda_orchestrator.name
}

output "log_group_digest" {
  description = "Nome do log group da Lambda digest"
  value       = aws_cloudwatch_log_group.lambda_digest.name
}

output "log_group_feedback" {
  description = "Nome do log group da Lambda feedback"
  value       = aws_cloudwatch_log_group.lambda_feedback.name
}

output "log_group_api_gateway" {
  description = "Nome do log group do API Gateway"
  value       = aws_cloudwatch_log_group.api_gateway.name
}

# Environment Info
output "environment" {
  description = "Ambiente deployado"
  value       = var.environment
}

output "aws_region" {
  description = "Região AWS"
  value       = var.aws_region
}

output "name_prefix" {
  description = "Prefixo usado para nomear recursos"
  value       = local.name_prefix
}

# Deployment Instructions
output "deployment_instructions" {
  description = "Próximos passos após deploy"
  value = <<-EOT
  
  ✅ Infraestrutura provisionada com sucesso!
  
  📋 PRÓXIMOS PASSOS:
  
  1. Atualizar secrets no AWS Secrets Manager:
     - Evolution API: ${aws_secretsmanager_secret.evolution_api.name}
     - SendPulse: ${aws_secretsmanager_secret.sendpulse.name}
     - Webhook Auth: ${aws_secretsmanager_secret.webhook_auth.name}
  
  2. Deploy do código das Lambdas:
     - jaiminho_message_orchestrator: ${aws_lambda_function.message_orchestrator.function_name}
     - jaiminho_daily_digest: ${aws_lambda_function.daily_digest.function_name}
     - jaiminho_feedback_handler: ${aws_lambda_function.feedback_handler.function_name}
  
  3. Configurar webhook na Evolution API:
     URL: ${aws_apigatewayv2_stage.default.invoke_url}/webhook
  
  4. Inicializar banco de dados RDS:
     Endpoint: ${aws_db_instance.main.endpoint}
     Database: ${aws_db_instance.main.db_name}
  
  5. Configurar alarmes SNS (opcional):
     - Adicionar SNS topic ARNs nos CloudWatch Alarms
  
  6. Testar endpoints:
     - Health: ${aws_apigatewayv2_stage.default.invoke_url}/health
     - Webhook: ${aws_apigatewayv2_stage.default.invoke_url}/webhook
     - Feedback: ${aws_apigatewayv2_stage.default.invoke_url}/feedback
  
  EOT
}

