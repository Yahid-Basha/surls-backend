from models import ShortUrl, Visit
from sqlalchemy.orm import Session
from dotenv import load_dotenv
import os
import redis
import ssl

# Load environment variables from .env file
load_dotenv()

def update_visit_in_db(short_url: str, ip: str, ua: str, ref: str, country: str, city: str, db: Session):
    short_url_obj = db.query(ShortUrl).filter(ShortUrl.short_url == short_url).first()
    if short_url_obj:
        short_url_obj.visits += 1
        visit = Visit(
            short_url_id=short_url_obj.id,
            ip_address=ip,
            user_agent=ua,
            referrer=ref,
            country=country,
            city=city
        )
        db.add(visit)
        db.commit()

# Use environment variables (fallback to localhost for non-Docker dev)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_SSL = os.getenv("REDIS_SSL", "false").lower() == "true"
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

# Configure Redis connection with proper SSL support (matching app.py configuration)
redis_config = {
    "host": REDIS_HOST,
    "port": REDIS_PORT,
    "db": 0,
    "decode_responses": True,
    "socket_timeout": 10,
    "socket_connect_timeout": 10,
    "retry_on_timeout": True,
    "health_check_interval": 30
}

# Add SSL configuration for AWS ElastiCache Serverless
if REDIS_SSL:
    redis_config["ssl"] = True
    redis_config["ssl_cert_reqs"] = ssl.CERT_NONE
    redis_config["ssl_check_hostname"] = False

# Add password if provided
if REDIS_PASSWORD:
    redis_config["password"] = REDIS_PASSWORD

try:
    redis_client = redis.StrictRedis(**redis_config)
    print("Redis client created successfully in helpers.py")
except Exception as e:
    print(f"Error creating Redis client in helpers.py: {e}")
    redis_client = None

def sync_visits_to_db(db: Session):
    """
    Sync visit counters from Redis to database.
    Since AWS ElastiCache Serverless doesn't support KEYS command,
    we need to track visit keys differently.
    """
    if not redis_client:
        print("Redis client not available in sync_visits_to_db")
        return

    try:
        # Get all short URLs from database and check their Redis counters
        short_urls = db.query(ShortUrl).all()
        synced_count = 0
        
        for short_url_obj in short_urls:
            try:
                # Get visit count from Redis
                redis_key = f"visits:{short_url_obj.short_url}"
                visit_count = redis_client.get(redis_key)
                
                if visit_count is not None:
                    visit_count = int(visit_count)
                    
                    # Only update if Redis count is different from DB count
                    if short_url_obj.visits != visit_count:
                        print(f"Syncing {short_url_obj.short_url}: DB={short_url_obj.visits} -> Redis={visit_count}")
                        short_url_obj.visits = visit_count
                        synced_count += 1
                
            except Exception as e:
                print(f"Error syncing visits for {short_url_obj.short_url}: {e}")
                continue
        
        # Commit all changes at once
        if synced_count > 0:
            db.commit()
            print(f"Successfully synced {synced_count} visit counters to database")
        else:
            print("No visit counters needed syncing")
            
    except Exception as e:
        print(f"Error in sync_visits_to_db: {e}")
        db.rollback()