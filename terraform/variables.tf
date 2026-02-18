# -----------------------------------------------------------------------------
# General
# -----------------------------------------------------------------------------

variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment (dev, prod)"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "Environment must be dev or prod."
  }
}

variable "project_name" {
  description = "Project name used for resource naming and tagging"
  type        = string
  default     = "institutional-defi"
}

# -----------------------------------------------------------------------------
# EKS
# -----------------------------------------------------------------------------

variable "eks_cluster_version" {
  description = "Kubernetes version for EKS cluster"
  type        = string
  default     = "1.29"
}

variable "eks_node_instance_types" {
  description = "EC2 instance types for EKS managed node group"
  type        = list(string)
  default     = ["t3.medium", "t3a.medium"]
}

variable "eks_node_min_size" {
  description = "Minimum number of nodes in managed node group"
  type        = number
  default     = 2
}

variable "eks_node_max_size" {
  description = "Maximum number of nodes in managed node group"
  type        = number
  default     = 10
}

variable "eks_node_desired_size" {
  description = "Desired number of nodes in managed node group"
  type        = number
  default     = 3
}

# -----------------------------------------------------------------------------
# RDS
# -----------------------------------------------------------------------------

variable "app_db_instance_class" {
  description = "RDS instance class for application database"
  type        = string
  default     = "db.t3.medium"
}

variable "app_db_allocated_storage" {
  description = "Initial storage in GB for application database"
  type        = number
  default     = 20
}

variable "app_db_max_allocated_storage" {
  description = "Maximum storage in GB for application database auto-scaling"
  type        = number
  default     = 100
}

variable "temporal_db_instance_class" {
  description = "RDS instance class for Temporal database"
  type        = string
  default     = "db.t3.small"
}

variable "temporal_db_allocated_storage" {
  description = "Initial storage in GB for Temporal database"
  type        = number
  default     = 20
}

variable "temporal_db_max_allocated_storage" {
  description = "Maximum storage in GB for Temporal database auto-scaling"
  type        = number
  default     = 50
}

variable "db_multi_az" {
  description = "Enable Multi-AZ for RDS instances"
  type        = bool
  default     = false
}

variable "app_db_password" {
  description = "Password for the application database"
  type        = string
  sensitive   = true
}

variable "temporal_db_password" {
  description = "Password for the Temporal database"
  type        = string
  sensitive   = true
}

# -----------------------------------------------------------------------------
# ElastiCache (Redis)
# -----------------------------------------------------------------------------

variable "redis_node_type" {
  description = "ElastiCache node type for Redis"
  type        = string
  default     = "cache.t3.small"
}

variable "redis_num_cache_nodes" {
  description = "Number of cache nodes in Redis replication group"
  type        = number
  default     = 1
}

variable "redis_automatic_failover" {
  description = "Enable automatic failover for Redis (requires 2+ nodes)"
  type        = bool
  default     = false
}

# -----------------------------------------------------------------------------
# Networking
# -----------------------------------------------------------------------------

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "single_nat_gateway" {
  description = "Use a single NAT gateway (cost savings for non-prod)"
  type        = bool
  default     = true
}
