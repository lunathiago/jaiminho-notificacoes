# RDS PostgreSQL Configuration with Multi-Tenant Support

# DB Subnet Group
resource "aws_db_subnet_group" "main" {
  name_prefix = "${local.name_prefix}-"
  description = "Database subnet group for ${local.name_prefix}"
  subnet_ids  = aws_subnet.private[*].id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-db-subnet-group"
  })

  lifecycle {
    create_before_destroy = true
  }
}

# RDS Parameter Group for PostgreSQL
resource "aws_db_parameter_group" "main" {
  name_prefix = "${local.name_prefix}-"
  family      = "postgres15"
  description = "Custom parameter group for ${local.name_prefix}"

  # Performance tuning
  parameter {
    name  = "shared_preload_libraries"
    value = "pg_stat_statements"
  }

  parameter {
    name  = "log_statement"
    value = "all"
  }

  parameter {
    name  = "log_min_duration_statement"
    value = "1000" # Log queries slower than 1s
  }

  # Security - enforce SSL
  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-db-parameter-group"
  })

  lifecycle {
    create_before_destroy = true
  }
}

# Random password for RDS master user
resource "random_password" "db_master_password" {
  length  = 32
  special = true
  # Avoid characters that might cause issues in connection strings
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

# Store RDS master password in Secrets Manager
resource "aws_secretsmanager_secret" "db_master_password" {
  name_prefix             = "${local.name_prefix}-db-master-password-"
  description             = "Master password for RDS PostgreSQL instance"
  recovery_window_in_days = var.environment == "prod" ? 30 : 0

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-db-master-password"
  })
}

resource "aws_secretsmanager_secret_version" "db_master_password" {
  secret_id = aws_secretsmanager_secret.db_master_password.id
  secret_string = jsonencode({
    username = "jaiminho_admin"
    password = random_password.db_master_password.result
    engine   = "postgres"
    host     = aws_db_instance.main.address
    port     = aws_db_instance.main.port
    dbname   = var.db_name
  })
}

# RDS PostgreSQL Instance
resource "aws_db_instance" "main" {
  identifier_prefix = "${local.name_prefix}-"

  # Engine configuration
  engine               = "postgres"
  engine_version       = var.db_engine_version
  instance_class       = var.db_instance_class
  allocated_storage    = var.db_allocated_storage
  max_allocated_storage = var.db_max_allocated_storage
  storage_type         = "gp3"
  storage_encrypted    = true

  # Database configuration
  db_name  = var.db_name
  username = "jaiminho_admin"
  password = random_password.db_master_password.result
  port     = 5432

  # Network configuration
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false

  # Parameter and option groups
  parameter_group_name = aws_db_parameter_group.main.name

  # Backup configuration
  backup_retention_period   = var.db_backup_retention_period
  backup_window            = "03:00-04:00"
  maintenance_window       = "sun:04:00-sun:05:00"
  delete_automated_backups = var.environment != "prod"

  # Monitoring and logging
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
  monitoring_interval             = 60
  monitoring_role_arn            = aws_iam_role.rds_monitoring.arn
  performance_insights_enabled    = true
  performance_insights_retention_period = var.environment == "prod" ? 7 : 7

  # High availability
  multi_az = var.environment == "prod"

  # Security
  deletion_protection       = var.environment == "prod"
  skip_final_snapshot      = var.environment != "prod"
  final_snapshot_identifier = var.environment == "prod" ? "${local.name_prefix}-final-snapshot-${formatdate("YYYY-MM-DD-hhmm", timestamp())}" : null
  copy_tags_to_snapshot    = true

  # Auto minor version upgrade
  auto_minor_version_upgrade = true

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-postgres"
  })

  lifecycle {
    ignore_changes = [
      final_snapshot_identifier,
      password,
      engine_version
    ]
  }

  depends_on = [aws_iam_role_policy_attachment.rds_monitoring]
}

# IAM Role for RDS Enhanced Monitoring
resource "aws_iam_role" "rds_monitoring" {
  name_prefix = "rds-mon-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "monitoring.rds.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-rds-monitoring-role"
  })
}

resource "aws_iam_role_policy_attachment" "rds_monitoring" {
  role       = aws_iam_role.rds_monitoring.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

# CloudWatch Alarms for RDS
resource "aws_cloudwatch_metric_alarm" "rds_cpu" {
  alarm_name          = "${local.name_prefix}-rds-high-cpu"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = "300"
  statistic           = "Average"
  threshold           = "80"
  alarm_description   = "This metric monitors RDS CPU utilization"
  alarm_actions       = [] # Add SNS topic ARN for notifications

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.id
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "rds_storage" {
  alarm_name          = "${local.name_prefix}-rds-low-storage"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "FreeStorageSpace"
  namespace           = "AWS/RDS"
  period              = "300"
  statistic           = "Average"
  threshold           = "5000000000" # 5GB in bytes
  alarm_description   = "This metric monitors RDS free storage space"
  alarm_actions       = [] # Add SNS topic ARN for notifications

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.id
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "rds_connections" {
  alarm_name          = "${local.name_prefix}-rds-high-connections"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "DatabaseConnections"
  namespace           = "AWS/RDS"
  period              = "300"
  statistic           = "Average"
  threshold           = "80"
  alarm_description   = "This metric monitors RDS database connections"
  alarm_actions       = [] # Add SNS topic ARN for notifications

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.id
  }

  tags = local.common_tags
}
