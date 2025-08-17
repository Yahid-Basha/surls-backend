#!/usr/bin/env python3
"""
Redis performance optimization for EC2 micro instance
This patches your code to be more memory-efficient
"""

import re

def optimize_redis_usage():
    """Optimize Redis operations for micro instance"""
    
    print("=== Optimizing Redis for EC2 Micro Instance ===")
    
    # Read app.py
    with open('app.py', 'r') as f:
        content = f.read()
    
    # Add TTL to Redis keys to prevent memory leaks
    optimizations = [
        # Add expiration to URL cache (7 days)
        (
            r'redis_client\.set\(f"short:{short_url_obj\.short_url}", short_url_obj\.long_url\)',
            'redis_client.setex(f"short:{short_url_obj.short_url}", 604800, short_url_obj.long_url)  # 7 days TTL'
        ),
        # Add expiration to visit counters (7 days)
        (
            r'redis_client\.setnx\(f"visits:{short_url_obj\.short_url}", short_url_obj\.visits or 0\)',
            'redis_client.setex(f"visits:{short_url_obj.short_url}", 604800, short_url_obj.visits or 0)  # 7 days TTL'
        ),
        # Optimize health check interval for micro instance
        (
            r'"health_check_interval": 30',
            '"health_check_interval": 60  # Reduced frequency for micro instance'
        ),
        # Add connection pooling optimization
        (
            r'"socket_timeout": 10,',
            '"socket_timeout": 5,  # Faster timeout for micro instance'
        )
    ]
    
    for pattern, replacement in optimizations:
        content = re.sub(pattern, replacement, content)
    
    # Write optimized version
    with open('app.py', 'w') as f:
        f.write(content)
    
    print("✅ app.py optimized for micro instance")
    
    # Read helpers.py
    with open('helpers.py', 'r') as f:
        content = f.read()
    
    # Optimize sync frequency
    content = re.sub(
        r'@scheduler\.scheduled_job\(\'interval\', minutes=10',
        '@scheduler.scheduled_job(\'interval\', minutes=30',  # Less frequent for micro instance
        content
    )
    
    with open('helpers.py', 'w') as f:
        f.write(content)
    
    print("✅ helpers.py optimized for micro instance")
    print("")
    print("🎯 Optimizations applied:")
    print("  - TTL on Redis keys (prevents memory leaks)")
    print("  - Reduced connection timeouts")
    print("  - Less frequent background sync (30min instead of 10min)")
    print("  - Optimized health checks")
    print("")
    print("📊 Expected benefits:")
    print("  - Lower memory usage")
    print("  - Better performance on micro instance")
    print("  - Automatic cleanup of old data")

if __name__ == "__main__":
    optimize_redis_usage()