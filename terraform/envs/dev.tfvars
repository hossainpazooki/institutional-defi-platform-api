environment = "dev"

# EKS — smaller for dev
eks_node_instance_types = ["t3.medium"]
eks_node_min_size       = 2
eks_node_max_size       = 5
eks_node_desired_size   = 2

# RDS — smaller instances
app_db_instance_class         = "db.t3.small"
app_db_allocated_storage      = 20
app_db_max_allocated_storage  = 50
temporal_db_instance_class    = "db.t3.micro"
db_multi_az                   = false

# Redis — single node
redis_node_type          = "cache.t3.micro"
redis_num_cache_nodes    = 1
redis_automatic_failover = false

# Networking — single NAT for cost savings
single_nat_gateway = true
