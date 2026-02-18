# -----------------------------------------------------------------------------
# ALB Ingress Controller IRSA
# -----------------------------------------------------------------------------

module "alb_controller_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.0"

  role_name                              = "${var.project_name}-alb-controller"
  attach_load_balancer_controller_policy = true

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:aws-load-balancer-controller"]
    }
  }

  tags = {
    Component = "ingress"
  }
}

# -----------------------------------------------------------------------------
# External Secrets Operator IRSA
# -----------------------------------------------------------------------------

module "eso_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.0"

  role_name = "${var.project_name}-eso"

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["external-secrets:external-secrets"]
    }
  }

  tags = {
    Component = "secrets"
  }
}

resource "aws_iam_role_policy" "eso_secrets" {
  name = "${var.project_name}-eso-secrets"
  role = module.eso_irsa.iam_role_name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = "arn:aws:secretsmanager:${var.aws_region}:*:secret:${var.project_name}/*"
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# API Service Account IRSA
# -----------------------------------------------------------------------------

module "api_sa_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.0"

  role_name = "${var.project_name}-api-sa"

  oidc_providers = {
    main = {
      provider_arn = module.eks.oidc_provider_arn
      namespace_service_accounts = [
        "${var.project_name}:api-sa",
        "${var.project_name}-dev:api-sa-dev"
      ]
    }
  }

  tags = {
    Component = "application"
  }
}

resource "aws_iam_role_policy" "api_secrets" {
  name = "${var.project_name}-api-secrets"
  role = module.api_sa_irsa.iam_role_name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = "arn:aws:secretsmanager:${var.aws_region}:*:secret:${var.project_name}/*"
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# Worker Service Account IRSA
# -----------------------------------------------------------------------------

module "worker_sa_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.0"

  role_name = "${var.project_name}-worker-sa"

  oidc_providers = {
    main = {
      provider_arn = module.eks.oidc_provider_arn
      namespace_service_accounts = [
        "${var.project_name}:worker-sa",
        "${var.project_name}-dev:worker-sa-dev"
      ]
    }
  }

  tags = {
    Component = "application"
  }
}

resource "aws_iam_role_policy" "worker_secrets" {
  name = "${var.project_name}-worker-secrets"
  role = module.worker_sa_irsa.iam_role_name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = "arn:aws:secretsmanager:${var.aws_region}:*:secret:${var.project_name}/*"
      }
    ]
  })
}
