# EKS Deployment Guide

Deploy the Institutional DeFi Platform API to AWS EKS.

## Prerequisites

- AWS CLI v2 configured with appropriate credentials
- Terraform >= 1.5.0
- kubectl
- Helm 3
- kustomize
- GitHub repository secrets configured:
  - `AWS_ACCOUNT_ID` — AWS account number
  - `AWS_CD_ROLE_ARN` — IAM role ARN for GitHub Actions OIDC
  - `SLACK_WEBHOOK_URL` — Slack notifications (optional)
- GitHub environment `production` created with required reviewers

## 1. Terraform Setup

### Initialize S3 Backend

Create the S3 bucket for Terraform state before first run (lock file is stored in S3 via `use_lockfile = true`):

```bash
aws s3 mb s3://institutional-defi-terraform-state --region us-east-1
```

### Provision Infrastructure

```bash
cd terraform

# Dev environment
terraform init
terraform plan -var-file=envs/dev.tfvars \
  -var="app_db_password=YOUR_APP_DB_PASSWORD" \
  -var="temporal_db_password=YOUR_TEMPORAL_DB_PASSWORD"
terraform apply -var-file=envs/dev.tfvars \
  -var="app_db_password=YOUR_APP_DB_PASSWORD" \
  -var="temporal_db_password=YOUR_TEMPORAL_DB_PASSWORD"

# Production environment
terraform plan -var-file=envs/prod.tfvars \
  -var="app_db_password=YOUR_APP_DB_PASSWORD" \
  -var="temporal_db_password=YOUR_TEMPORAL_DB_PASSWORD"
terraform apply -var-file=envs/prod.tfvars \
  -var="app_db_password=YOUR_APP_DB_PASSWORD" \
  -var="temporal_db_password=YOUR_TEMPORAL_DB_PASSWORD"
```

> **Tip**: Store passwords in a gitignored `terraform/secrets.auto.tfvars` file instead of passing via CLI:
> ```hcl
> app_db_password      = "your-secure-password"
> temporal_db_password  = "your-secure-password"
> ```

### Key Outputs

After `terraform apply`, note these values:

| Output | Used For |
|--------|----------|
| `eks_cluster_name` | kubeconfig setup |
| `ecr_api_url` | Docker image push target |
| `ecr_worker_url` | Docker image push target |
| `app_db_endpoint` | Application DATABASE_URL |
| `temporal_db_endpoint` | Temporal persistence config |
| `redis_endpoint` | Application REDIS_URL |
| `alb_controller_role_arn` | ALB Controller Helm install |
| `eso_role_arn` | ESO Helm install |
| `api_sa_role_arn` | IRSA patches in kube overlays |
| `worker_sa_role_arn` | IRSA patches in kube overlays |

## 2. Post-Terraform Setup

### Populate Secrets Manager

Terraform creates the secrets with auto-populated DB/Redis URLs. Set the Anthropic API key manually:

```bash
aws secretsmanager put-secret-value \
  --secret-id institutional-defi/anthropic \
  --secret-string '{"api_key":"sk-ant-your-actual-key"}'
```

### Create Temporal Visibility Database

Temporal requires a separate `temporal_visibility` database on the same RDS instance:

```bash
TEMPORAL_ENDPOINT=$(terraform output -raw temporal_db_endpoint)
psql "postgresql://temporal:PASSWORD@${TEMPORAL_ENDPOINT}/temporal" \
  -c "CREATE DATABASE temporal_visibility;"
```

### Update IRSA Annotations

Replace `ACCOUNT_ID` placeholders in kube overlay patches with your actual AWS account ID:

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
sed -i "s/ACCOUNT_ID/${ACCOUNT_ID}/g" kube/overlays/dev/kustomization.yaml
sed -i "s/ACCOUNT_ID/${ACCOUNT_ID}/g" kube/overlays/prod/kustomization.yaml
```

## 3. Cluster Bootstrap

### Configure kubectl

```bash
aws eks update-kubeconfig --name institutional-defi-eks --region us-east-1
```

### Install AWS Load Balancer Controller

```bash
ALB_ROLE_ARN=$(terraform output -raw alb_controller_role_arn)

helm repo add eks https://aws.github.io/eks-charts
helm repo update

helm install aws-load-balancer-controller eks/aws-load-balancer-controller \
  -n kube-system \
  --set clusterName=institutional-defi-eks \
  --set serviceAccount.create=true \
  --set serviceAccount.name=aws-load-balancer-controller \
  --set serviceAccount.annotations."eks\.amazonaws\.com/role-arn"=$ALB_ROLE_ARN
```

### Install External Secrets Operator

```bash
ESO_ROLE_ARN=$(terraform output -raw eso_role_arn)

helm repo add external-secrets https://charts.external-secrets.io
helm repo update

helm install external-secrets external-secrets/external-secrets \
  -n external-secrets --create-namespace \
  --set serviceAccount.annotations."eks\.amazonaws\.com/role-arn"=$ESO_ROLE_ARN
```

### Apply ClusterSecretStore

```bash
kubectl apply -f kube/cluster/cluster-secret-store.yaml
```

## 4. Deploy Temporal

```bash
TEMPORAL_ENDPOINT=$(terraform output -raw temporal_db_endpoint)

helm repo add temporalio https://temporal.io/helm-charts
helm repo update

helm install temporal temporalio/temporal \
  -n temporal --create-namespace \
  -f kube/temporal/values.yaml \
  --set server.config.persistence.default.sql.host=$TEMPORAL_ENDPOINT \
  --set server.config.persistence.default.sql.password=TEMPORAL_DB_PASSWORD \
  --set server.config.persistence.visibility.sql.host=$TEMPORAL_ENDPOINT \
  --set server.config.persistence.visibility.sql.password=TEMPORAL_DB_PASSWORD
```

## 5. Deploy Application

### Staging (automatic)

Push to `main` branch. The `cd-staging.yml` workflow will:
1. Build and push Docker images to ECR
2. Run Trivy security scan
3. Deploy to dev namespace
4. Run health check
5. Notify via Slack

### Production (manual)

Trigger the `cd-production.yml` workflow with a semver tag:

```bash
# Tag and push a release
git tag v1.0.0
git push origin v1.0.0

# Then trigger via GitHub UI or CLI
gh workflow run cd-production.yml -f image_tag=v1.0.0
```

The workflow requires approval from the `production` environment reviewers.

### Database Migrations

Run Alembic migrations after deploying new code:

```bash
kubectl exec -it deployment/api -n institutional-defi -- alembic upgrade head
```

## 6. Monitoring

### Health Check

```bash
# Via kubectl
kubectl exec -it deployment/api -n institutional-defi -- curl localhost:8000/health

# Via ALB
curl https://api.institutional-defi.example.com/health
```

### Prometheus Metrics

Temporal exports Prometheus metrics. Scrape from the Temporal frontend service on port 9090.

### Temporal Web UI

Access via internal ALB at `temporal.institutional-defi.internal` (requires VPN or bastion).

### CloudWatch Logs

EKS node logs are automatically sent to CloudWatch via the VPC CNI plugin.

## 7. Troubleshooting

### IRSA Trust Policy Issues

```bash
# Verify the OIDC provider is configured
aws eks describe-cluster --name institutional-defi-eks \
  --query "cluster.identity.oidc.issuer" --output text

# Check SA annotations
kubectl get sa api-sa -n institutional-defi -o yaml
```

### ExternalSecret Not Syncing

```bash
# Check ESO logs
kubectl logs -n external-secrets -l app.kubernetes.io/name=external-secrets

# Check ExternalSecret status
kubectl get externalsecret -n institutional-defi -o yaml
```

### ALB Target Group Unhealthy

```bash
# Check pod health
kubectl get pods -n institutional-defi
kubectl describe pod <pod-name> -n institutional-defi

# Check ingress status
kubectl get ingress -n institutional-defi -o yaml
```

### Pod CrashLoopBackOff

```bash
kubectl logs <pod-name> -n institutional-defi --previous
kubectl describe pod <pod-name> -n institutional-defi
```

## 8. Quick Commands

```bash
# Deploy (staging — automatic on push to main)
git push origin main

# Deploy (production — manual)
gh workflow run cd-production.yml -f image_tag=v1.0.0

# Rollback
kubectl rollout undo deployment/api -n institutional-defi
kubectl rollout undo deployment/worker -n institutional-defi

# Scale
kubectl scale deployment/api --replicas=5 -n institutional-defi

# Debug
kubectl exec -it deployment/api -n institutional-defi -- /bin/bash

# Temporal management
kubectl exec -it deployment/temporal-frontend -n temporal -- tctl namespace list
kubectl exec -it deployment/temporal-frontend -n temporal -- tctl workflow list
```

## 9. Cost Estimate (Production)

| Resource | Monthly Cost |
|----------|-------------|
| EKS control plane | ~$73 |
| EC2 nodes (3x t3.medium) | ~$90 |
| ALB | ~$25 |
| RDS (app + temporal) | ~$80-100 |
| ElastiCache (2 nodes) | ~$25 |
| NAT Gateway (3 AZs) | ~$105 |
| ECR | ~$5-10 |
| **Total** | **~$400-430/mo** |

Dev environment with single NAT and smaller instances: ~$200-250/mo.

## 10. Notes

- **TimescaleDB**: AWS RDS does not support TimescaleDB natively. The application gracefully degrades (hypertable creation silently skipped). For full TimescaleDB support, use Timescale Cloud or self-managed PostgreSQL.
- **Security scans**: Weekly automated scans run via `security-scan.yml` (dependency audit, SAST, secrets, container, IaC).
- **IRSA**: All service accounts use IAM Roles for Service Accounts — no node-level credentials needed.
