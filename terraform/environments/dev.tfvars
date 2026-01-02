# Ambiente de Desenvolvimento
environment  = "dev"
aws_region   = "us-east-1"
cost_center  = "engineering"

# Lambda - Recursos reduzidos para dev
lambda_memory_size = 256
lambda_timeout     = 30

# RDS - Instância menor para dev
db_instance_class           = "db.t4g.micro"
db_allocated_storage        = 20
db_max_allocated_storage    = 50
db_backup_retention_period  = 3

# Network
availability_zones = ["us-east-1a"]

# SQS
sqs_message_retention_seconds  = 345600 # 4 dias
sqs_visibility_timeout_seconds = 180

# EventBridge - Apenas para testes
daily_digest_schedule = "cron(0 10 * * ? *)" # 10 AM UTC

# API Gateway - Limites menores
api_throttle_burst_limit = 50
api_throttle_rate_limit  = 25

