#!/bin/bash
# Redis setup script for EC2 micro instance
# Optimized for minimal memory usage

echo "=== Redis Setup for EC2 Micro Instance ==="
echo "This script will:"
echo "1. Install Redis on your EC2 instance"
echo "2. Configure it for minimal memory usage"
echo "3. Set up security and persistence"
echo ""

# Install Redis (Ubuntu/Amazon Linux)
echo "Installing Redis..."
if command -v yum &> /dev/null; then
    # Amazon Linux
    sudo yum update -y
    sudo yum install redis -y
elif command -v apt &> /dev/null; then
    # Ubuntu
    sudo apt update
    sudo apt install redis-server -y
fi

# Create optimized Redis configuration
echo "Creating optimized Redis config for micro instance..."

sudo tee /etc/redis/redis-micro.conf > /dev/null << 'EOF'
# Redis configuration optimized for t2.micro/t3.micro EC2 instance
# Memory-efficient settings for URL shortener

# Basic settings
port 6379
bind 127.0.0.1 ::1
protected-mode yes
timeout 300

# Memory optimization for micro instance
maxmemory 800mb                    # Reserve 200mb for system
maxmemory-policy allkeys-lru       # Evict least recently used keys when memory is full

# Persistence (for data safety)
save 900 1                         # Save if at least 1 key changed in 900 seconds
save 300 10                        # Save if at least 10 keys changed in 300 seconds
save 60 10000                      # Save if at least 10000 keys changed in 60 seconds

# Disk persistence settings
dir /var/lib/redis
dbfilename dump.rdb
rdbcompression yes
rdbchecksum yes

# Network and performance
tcp-keepalive 300
tcp-backlog 511

# Logging
loglevel notice
logfile /var/log/redis/redis-server.log

# Security (basic)
# requirepass your_password_here    # Uncomment and set password

# Disable dangerous commands
rename-command FLUSHDB ""
rename-command FLUSHALL ""
rename-command DEBUG ""
rename-command CONFIG "CONFIG_ec2_redis_2024"

# Client connection limits
maxclients 100                     # Limit concurrent connections

# Slow log
slowlog-log-slower-than 10000      # Log queries slower than 10ms
slowlog-max-len 128

# Memory usage tracking
# latency-monitor-threshold 100

EOF

# Set permissions
sudo chown redis:redis /etc/redis/redis-micro.conf
sudo chmod 640 /etc/redis/redis-micro.conf

# Create systemd service for optimized Redis
sudo tee /etc/systemd/system/redis-micro.service > /dev/null << 'EOF'
[Unit]
Description=Redis In-Memory Data Store (Micro Instance Optimized)
After=network.target

[Service]
User=redis
Group=redis
ExecStart=/usr/bin/redis-server /etc/redis/redis-micro.conf
ExecStop=/usr/bin/redis-cli shutdown
Restart=always
RestartSec=3

# Memory and CPU limits for micro instance
MemoryLimit=850M
CPUQuota=80%

[Install]
WantedBy=multi-user.target
EOF

# Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable redis-micro
sudo systemctl start redis-micro

echo ""
echo "✅ Redis installed and configured for micro instance!"
echo ""
echo "Configuration highlights:"
echo "- Max memory: 800MB (saves 200MB for system)"
echo "- LRU eviction policy (automatic cleanup)"
echo "- Optimized persistence settings"
echo "- Connection limits to prevent overload"
echo ""
echo "Check status:"
echo "  sudo systemctl status redis-micro"
echo ""
echo "Test connection:"
echo "  redis-cli ping"
echo ""
echo "Monitor memory usage:"
echo "  redis-cli info memory"
echo ""
echo "Don't forget to:"
echo "1. Update your .env file with EC2 private IP"
echo "2. Configure security groups (port 6379)"
echo "3. Set up monitoring for memory usage"