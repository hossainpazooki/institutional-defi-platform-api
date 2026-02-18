# -----------------------------------------------------------------------------
# AWS Secrets Manager — matches kube/base/api/external-secret.yaml refs
# -----------------------------------------------------------------------------

# Database URL — auto-populated with RDS endpoint
resource "aws_secretsmanager_secret" "database" {
  name        = "${var.project_name}/database"
  description = "Application database connection string"

  tags = {
    Component = "secrets"
  }
}

resource "aws_secretsmanager_secret_version" "database" {
  secret_id = aws_secretsmanager_secret.database.id
  secret_string = jsonencode({
    url = "postgresql://${module.app_db.db_instance_username}:${var.app_db_password}@${module.app_db.db_instance_endpoint}/${module.app_db.db_instance_name}"
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# Redis URL — auto-populated with ElastiCache endpoint
resource "aws_secretsmanager_secret" "redis" {
  name        = "${var.project_name}/redis"
  description = "Redis connection string"

  tags = {
    Component = "secrets"
  }
}

resource "aws_secretsmanager_secret_version" "redis" {
  secret_id = aws_secretsmanager_secret.redis.id
  secret_string = jsonencode({
    url = "redis://${aws_elasticache_replication_group.redis.primary_endpoint_address}:6379/0"
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# Anthropic API Key — created empty, set manually
resource "aws_secretsmanager_secret" "anthropic" {
  name        = "${var.project_name}/anthropic"
  description = "Anthropic API key for LLM decoder"

  tags = {
    Component = "secrets"
  }
}

resource "aws_secretsmanager_secret_version" "anthropic" {
  secret_id = aws_secretsmanager_secret.anthropic.id
  secret_string = jsonencode({
    api_key = "REPLACE_ME"
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}
