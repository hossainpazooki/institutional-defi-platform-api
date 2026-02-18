data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, 3)
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "${var.project_name}-vpc"
  cidr = var.vpc_cidr

  azs              = local.azs
  private_subnets  = [for i, az in local.azs : cidrsubnet(var.vpc_cidr, 8, i + 1)]
  public_subnets   = [for i, az in local.azs : cidrsubnet(var.vpc_cidr, 8, i + 101)]
  database_subnets = [for i, az in local.azs : cidrsubnet(var.vpc_cidr, 8, i + 201)]

  # NAT gateway — single for dev, per-AZ for prod
  enable_nat_gateway     = true
  single_nat_gateway     = var.single_nat_gateway
  one_nat_gateway_per_az = !var.single_nat_gateway

  # DNS
  enable_dns_hostnames = true
  enable_dns_support   = true

  # Database subnet group for RDS
  create_database_subnet_group = true
  database_subnet_group_name   = "${var.project_name}-db"

  # EKS subnet tags
  public_subnet_tags = {
    "kubernetes.io/role/elb"                              = 1
    "kubernetes.io/cluster/${var.project_name}-eks"       = "shared"
  }

  private_subnet_tags = {
    "kubernetes.io/role/internal-elb"                     = 1
    "kubernetes.io/cluster/${var.project_name}-eks"       = "shared"
  }

  tags = {
    Component = "networking"
  }
}
