# -----------------------------------------------------------------------------
# Redis 7.0 Replication Group
# -----------------------------------------------------------------------------

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "${var.project_name}-redis"
  description          = "Redis for ${var.project_name} caching and Celery broker"

  engine               = "redis"
  engine_version       = "7.0"
  node_type            = var.redis_node_type
  num_cache_clusters   = var.redis_num_cache_nodes
  parameter_group_name = "default.redis7"
  port                 = 6379

  # Networking
  subnet_group_name  = aws_elasticache_subnet_group.redis.name
  security_group_ids = [aws_security_group.redis.id]

  # Failover (requires 2+ nodes)
  automatic_failover_enabled = var.redis_automatic_failover

  # Encryption at rest, no TLS transit (app uses redis:// not rediss://)
  at_rest_encryption_enabled = true
  transit_encryption_enabled = false

  # Maintenance
  maintenance_window       = "Mon:05:00-Mon:06:00"
  snapshot_retention_limit = var.environment == "prod" ? 7 : 1
  snapshot_window          = "02:00-03:00"

  tags = {
    Component = "cache"
  }
}

# Subnet group — database subnets
resource "aws_elasticache_subnet_group" "redis" {
  name       = "${var.project_name}-redis"
  subnet_ids = module.vpc.database_subnets

  tags = {
    Component = "cache"
  }
}

# Security group — only EKS nodes can reach port 6379
resource "aws_security_group" "redis" {
  name_prefix = "${var.project_name}-redis-"
  description = "Allow Redis access from EKS nodes"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description     = "Redis from EKS nodes"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [module.eks.node_security_group_id]
  }

  tags = {
    Name      = "${var.project_name}-redis"
    Component = "cache"
  }

  lifecycle {
    create_before_destroy = true
  }
}
