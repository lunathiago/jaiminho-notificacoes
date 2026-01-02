# Ambiente de Staging
environment  = "staging"
aws_region   = "us-east-1"
cost_center  = "engineering"

# Lambda - Recursos moderados para staging
lambda_memory_size = 512
lambda_timeout     = 60

# RDS - Instância média para staging
db_instance_class           = "db.t4g.small"
db_allocated_storage        = 50
db_max_allocated_storage    = 100
db_backup_retention_period  = 7

# Network
availability_zones = ["us-east-1a", "us-east-1b"]

# SQS
sqs_message_retention_seconds  = 1209600 # 14 dias
sqs_visibility_timeout_seconds = 300

# EventBridge
daily_digest_schedule = "cron(0 9 * * ? *)" # 9 AM UTC

# API Gateway
api_throttle_burst_limit = 100
api_throttle_rate_limit  = 50

