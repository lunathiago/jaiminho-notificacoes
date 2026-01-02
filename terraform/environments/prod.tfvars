# Ambiente de Produção
environment  = "prod"
aws_region   = "us-east-1"
cost_center  = "production"

# Lambda - Recursos otimizados para prod
lambda_memory_size = 1024
lambda_timeout     = 60

# RDS - Instância com alta disponibilidade
db_instance_class           = "db.t4g.medium"
db_allocated_storage        = 100
db_max_allocated_storage    = 500
db_backup_retention_period  = 30

# Network - Múltiplas AZs para alta disponibilidade
availability_zones = ["us-east-1a", "us-east-1b", "us-east-1c"]

# SQS
sqs_message_retention_seconds  = 1209600 # 14 dias
sqs_visibility_timeout_seconds = 300

# EventBridge
daily_digest_schedule = "cron(0 9 * * ? *)" # 9 AM UTC (6 AM BRT)

# API Gateway - Limites mais altos para prod
api_throttle_burst_limit = 200
api_throttle_rate_limit  = 100

