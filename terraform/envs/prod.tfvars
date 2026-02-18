environment = "prod"

# EKS — production sizing
eks_node_instance_types = ["t3.medium", "t3a.medium"]
eks_node_min_size       = 3
eks_node_max_size       = 10
eks_node_desired_size   = 3

# RDS — production instances with Multi-AZ
app_db_instance_class         = "db.t3.medium"
app_db_allocated_storage      = 20
app_db_max_allocated_storage  = 100
temporal_db_instance_class    = "db.t3.small"
db_multi_az                   = true

# Redis — 2 nodes with failover
redis_node_type          = "cache.t3.small"
redis_num_cache_nodes    = 2
redis_automatic_failover = true

# Networking — NAT per AZ for HA
single_nat_gateway = false
