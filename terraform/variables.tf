variable "project_name" {
  description = "Nome do projeto"
  type        = string
  default     = "jaiminho-notificacoes"
}

variable "environment" {
  description = "Ambiente (dev, staging, prod)"
  type        = string

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment deve ser dev, staging ou prod."
  }
}

variable "aws_region" {
  description = "Região AWS"
  type        = string
  default     = "us-east-1"
}

variable "cost_center" {
  description = "Centro de custo para billing"
  type        = string
  default     = "engineering"
}

# Lambda Configuration
variable "lambda_runtime" {
  description = "Runtime do Lambda"
  type        = string
  default     = "python3.11"
}

variable "lambda_memory_size" {
  description = "Memória alocada para Lambda functions (MB)"
  type        = number
  default     = 512
}

variable "lambda_timeout" {
  description = "Timeout para Lambda functions (segundos)"
  type        = number
  default     = 60
}

# RDS Configuration
variable "db_instance_class" {
  description = "Classe da instância RDS"
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage" {
  description = "Storage alocado para RDS (GB)"
  type        = number
  default     = 20
}

variable "db_max_allocated_storage" {
  description = "Storage máximo para autoscaling (GB)"
  type        = number
  default     = 100
}

variable "db_engine_version" {
  description = "Versão do PostgreSQL"
  type        = string
  default     = "15.3"
}

variable "db_backup_retention_period" {
  description = "Período de retenção de backup (dias)"
  type        = number
  default     = 7
}

variable "db_name" {
  description = "Nome do banco de dados"
  type        = string
  default     = "jaiminho"
}

# Network Configuration
variable "vpc_cidr" {
  description = "CIDR block para VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Availability Zones"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

# SQS Configuration
variable "sqs_message_retention_seconds" {
  description = "Tempo de retenção de mensagens no SQS (segundos)"
  type        = number
  default     = 1209600 # 14 dias
}

variable "sqs_visibility_timeout_seconds" {
  description = "Timeout de visibilidade do SQS (segundos)"
  type        = number
  default     = 300 # 5 minutos
}

# EventBridge Configuration
variable "daily_digest_schedule" {
  description = "Cron expression para daily digest"
  type        = string
  default     = "cron(0 9 * * ? *)" # 9 AM UTC diariamente
}

# API Gateway Configuration
variable "api_throttle_burst_limit" {
  description = "API Gateway burst limit"
  type        = number
  default     = 100
}

variable "api_throttle_rate_limit" {
  description = "API Gateway rate limit (requests por segundo)"
  type        = number
  default     = 50
}
