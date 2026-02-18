# -----------------------------------------------------------------------------
# Application Database (PostgreSQL 16)
# -----------------------------------------------------------------------------

module "app_db" {
  source  = "terraform-aws-modules/rds/aws"
  version = "~> 6.0"

  identifier = "${var.project_name}-app"

  engine               = "postgres"
  engine_version       = "16"
  family               = "postgres16"
  major_engine_version = "16"
  instance_class       = var.app_db_instance_class

  allocated_storage     = var.app_db_allocated_storage
  max_allocated_storage = var.app_db_max_allocated_storage

  db_name                     = "institutional_defi"
  username                    = "app"
  password                    = var.app_db_password
  manage_master_user_password = false
  port                        = 5432

  multi_az               = var.db_multi_az
  db_subnet_group_name   = module.vpc.database_subnet_group_name
  vpc_security_group_ids = [aws_security_group.rds.id]

  # Backups
  backup_retention_period = var.environment == "prod" ? 14 : 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "Mon:04:00-Mon:05:00"

  # Encryption
  storage_encrypted = true

  # Deletion protection
  deletion_protection = var.environment == "prod"
  skip_final_snapshot = var.environment != "prod"

  # Performance Insights
  performance_insights_enabled = true

  # Parameters — note: TimescaleDB not available on RDS.
  # App degrades gracefully (src/database.py:138-140).
  parameters = [
    {
      name  = "shared_preload_libraries"
      value = "pg_stat_statements"
    }
  ]

  tags = {
    Component = "database"
    Database  = "application"
  }
}

# -----------------------------------------------------------------------------
# Temporal Database (PostgreSQL 16)
# -----------------------------------------------------------------------------

module "temporal_db" {
  source  = "terraform-aws-modules/rds/aws"
  version = "~> 6.0"

  identifier = "${var.project_name}-temporal"

  engine               = "postgres"
  engine_version       = "16"
  family               = "postgres16"
  major_engine_version = "16"
  instance_class       = var.temporal_db_instance_class

  allocated_storage     = var.temporal_db_allocated_storage
  max_allocated_storage = var.temporal_db_max_allocated_storage

  db_name                     = "temporal"
  username                    = "temporal"
  password                    = var.temporal_db_password
  manage_master_user_password = false
  port                        = 5432

  multi_az               = var.db_multi_az
  db_subnet_group_name   = module.vpc.database_subnet_group_name
  vpc_security_group_ids = [aws_security_group.rds.id]

  # Backups
  backup_retention_period = 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "Mon:04:00-Mon:05:00"

  # Encryption
  storage_encrypted = true

  # Deletion protection
  deletion_protection = var.environment == "prod"
  skip_final_snapshot = var.environment != "prod"

  tags = {
    Component = "database"
    Database  = "temporal"
  }
}

# -----------------------------------------------------------------------------
# RDS Security Group — only EKS nodes can reach port 5432
# -----------------------------------------------------------------------------

resource "aws_security_group" "rds" {
  name_prefix = "${var.project_name}-rds-"
  description = "Allow PostgreSQL access from EKS nodes"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description     = "PostgreSQL from EKS nodes"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [module.eks.node_security_group_id]
  }

  tags = {
    Name      = "${var.project_name}-rds"
    Component = "database"
  }

  lifecycle {
    create_before_destroy = true
  }
}
