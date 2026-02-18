module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = "${var.project_name}-eks"
  cluster_version = var.eks_cluster_version

  # Networking
  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  # Endpoint access
  cluster_endpoint_public_access  = true
  cluster_endpoint_private_access = true

  # IRSA
  enable_irsa = true

  # Cluster addons
  cluster_addons = {
    coredns = {
      most_recent = true
    }
    kube-proxy = {
      most_recent = true
    }
    vpc-cni = {
      most_recent = true
    }
    aws-ebs-csi-driver = {
      most_recent              = true
      service_account_role_arn = module.ebs_csi_irsa.iam_role_arn
    }
  }

  # Managed node group
  eks_managed_node_groups = {
    default = {
      name            = "${var.project_name}-nodes"
      instance_types  = var.eks_node_instance_types
      capacity_type   = "ON_DEMAND"

      min_size     = var.eks_node_min_size
      max_size     = var.eks_node_max_size
      desired_size = var.eks_node_desired_size

      labels = {
        Environment = var.environment
        Project     = var.project_name
      }
    }
  }

  # Allow access from the node security group to RDS and ElastiCache
  node_security_group_additional_rules = {
    egress_rds = {
      description                  = "Node to RDS"
      protocol                     = "tcp"
      from_port                    = 5432
      to_port                      = 5432
      type                         = "egress"
      source_cluster_security_group = false
      cidr_blocks                  = [var.vpc_cidr]
    }
    egress_redis = {
      description                  = "Node to Redis"
      protocol                     = "tcp"
      from_port                    = 6379
      to_port                      = 6379
      type                         = "egress"
      source_cluster_security_group = false
      cidr_blocks                  = [var.vpc_cidr]
    }
  }

  tags = {
    Component = "compute"
  }
}

# EBS CSI Driver IRSA
module "ebs_csi_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.0"

  role_name             = "${var.project_name}-ebs-csi"
  attach_ebs_csi_policy = true

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:ebs-csi-controller-sa"]
    }
  }

  tags = {
    Component = "storage"
  }
}
