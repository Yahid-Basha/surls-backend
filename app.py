import os
import string
import random
import requests
from helpers import sync_visits_to_db, update_visit_in_db
import redis
import ssl
import re
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from models import ShortUrl, Base, Visit
from database import engine, get_db, SessionLocal
from schema import ShortUrlResponse
from fastapi import BackgroundTasks
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

Base.metadata.create_all(bind=engine)

class longUrl(BaseModel):
    url: str

app = APIRouter()

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_SSL = os.getenv("REDIS_SSL", "false").lower() == "true"
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

print(f"Connecting to Redis at {REDIS_HOST}:{REDIS_PORT} (SSL: {REDIS_SSL})")

# Configure Redis connection with proper timeout and SSL support for AWS ElastiCache
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

# Add SSL configuration for AWS ElastiCache Serverless (matches redis-cli --tls)
if REDIS_SSL:
    redis_config["ssl"] = True
    redis_config["ssl_cert_reqs"] = ssl.CERT_NONE  # Equivalent to redis-cli --tls behavior
    redis_config["ssl_check_hostname"] = False

# Add password if provided
if REDIS_PASSWORD:
    redis_config["password"] = REDIS_PASSWORD

try:
    redis_client = redis.StrictRedis(**redis_config)
    print("Redis client created successfully")
except Exception as e:
    print(f"Error creating Redis client: {e}")
    redis_client = None

def check_redis_connection():
    """
    Check if Redis connection is established and working.
    Returns True if connected, False otherwise.
    """
    if redis_client is None:
        print("Redis client is not initialized")
        return False
    
    try:
        # Ping Redis to verify connection (with timeout)
        response = redis_client.ping()
        if response:
            print("Successfully connected to Redis")
            return True
        return False
    except redis.ConnectionError as e:
        print(f"Failed to connect to Redis: {e}")
        return False
    except redis.TimeoutError as e:
        print(f"Redis connection timed out: {e}")
        return False
    except ssl.SSLError as e:
        print(f"SSL error connecting to Redis: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error connecting to Redis: {e}")
        return False

# Test connection on startup
connected = check_redis_connection()
if not connected:
    print(f"WARNING: Could not connect to Redis at {REDIS_HOST}:{REDIS_PORT}")
else:
    # Test Redis functionality
    if redis_client:
        try:
            # Test basic operations
            test_key = "app_test_key"
            test_value = "app_test_value"
            redis_client.set(test_key, test_value)
            retrieved_value = redis_client.get(test_key)
            print(f"Redis test: Set '{test_key}' = '{test_value}', Retrieved: '{retrieved_value}'")
            
            # Check current database
            info = redis_client.info()
            print(f"Connected to Redis DB: {redis_config.get('db', 0)}")
            
            # List some keys for debugging
            keys = redis_client.keys("*")
            print(f"Current keys in Redis DB {redis_config.get('db', 0)}: {keys[:10]}")  # Show first 10 keys
            
        except Exception as e:
            print(f"Error testing Redis: {e}")

def get_geo_from_ip(ip: str):
    try:
        res = requests.get(f"http://ip-api.com/json/{ip}")
        data = res.json()
        if data.get("status") == "success":
            return data.get("countryCode"), data.get("city")
    except:
        pass
    return None, None

@app.get("/")
def read_root():
    return {"message": "Hello, World!"}

@app.get("/redis/test")
def test_redis():
    """Test endpoint to verify Redis connectivity and operations"""
    if not redis_client:
        return {"error": "Redis client not available"}
    
    try:
        # Test basic operations
        test_key = "manual_test_key"
        test_value = f"test_value_{random.randint(1000, 9999)}"
        
        # Set a value
        redis_client.set(test_key, test_value)
        
        # Get the value back
        retrieved = redis_client.get(test_key)
        
        # Get some info
        info = redis_client.info()
        keys = redis_client.keys("*")
        
        return {
            "redis_connected": True,
            "test_set": test_value,
            "test_retrieved": retrieved,
            "db_number": redis_config.get('db', 0),
            "total_keys": len(keys),
            "sample_keys": keys[:10],
            "redis_version": info.get('redis_version', 'unknown')
        }
    except Exception as e:
        return {"error": f"Redis error: {str(e)}"}

@app.post("/url/shorten", response_model=ShortUrlResponse)
def shorten_url(long_url: longUrl, db: Session = Depends(get_db)):
    short_url = short_url_generator(db)

    short_url_obj = ShortUrl(
        short_url=short_url,
        long_url=long_url.url,
        user_id=None
    )
    db.add(short_url_obj)
    db.commit()
    
    # Store in Redis if available
    if redis_client:
        try:
            redis_client.set(f"short:{short_url_obj.short_url}", short_url_obj.long_url)
            # Also init visits counter in Redis (set if not exists)
            redis_client.setnx(f"visits:{short_url_obj.short_url}", short_url_obj.visits or 0)
        except Exception as e:
            print(f"Error storing in Redis: {e}")
    
    return short_url_obj

def short_url_generator(db: Session):
    characters = string.ascii_letters + string.digits
    random_string = ''.join(random.choice(characters) for _ in range(6))
    while db.query(ShortUrl).filter(ShortUrl.short_url == random_string).first():
        random_string = ''.join(random.choice(characters) for _ in range(6))
    return random_string

@app.get("/{short_url}")
def redirect_to_long_url(short_url: str, request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if not re.fullmatch(r"[A-Za-z0-9]{6}", short_url):
        raise HTTPException(status_code=400, detail="Invalid short URL format")

    ip = request.headers.get("X-Forwarded-For", request.client.host)

    # Try Redis first if available
    long_url = None
    if redis_client:
        try:
            long_url = redis_client.get(f"short:{short_url}")
            if long_url:
                redis_client.incr(f"visits:{short_url}")
                background_tasks.add_task(
                    update_visit_in_db,
                    short_url,
                    ip,
                    request.headers.get("User-Agent", ""),
                    request.headers.get("Referer", ""),
                    *get_geo_from_ip(ip),
                    db
                )
                return RedirectResponse(long_url, status_code=302)
        except Exception as e:
            print(f"Error accessing Redis: {e}")

    # Cache miss or Redis unavailable - fallback to database
    short_url_obj = db.query(ShortUrl).filter(ShortUrl.short_url == short_url).first()
    if not short_url_obj:
        raise HTTPException(status_code=404, detail="URL not found")

    # Update Redis cache if available
    if redis_client:
        try:
            redis_client.set(f"short:{short_url}", short_url_obj.long_url)
            redis_client.set(f"visits:{short_url}", short_url_obj.visits or 0)
            redis_client.incr(f"visits:{short_url}")
        except Exception as e:
            print(f"Error updating Redis cache: {e}")

    background_tasks.add_task(
        update_visit_in_db,
        short_url,
        request.client.host,
        request.headers.get("User-Agent", ""),
        request.headers.get("Referer", ""),
        *get_geo_from_ip(request.client.host),
        db
    )

    return RedirectResponse(short_url_obj.long_url, status_code=302)


@app.get("/usr/{uid}")
def get_stats(uid: str, db: Session = Depends(get_db)):
    short_url_obj = db.query(ShortUrl).filter(ShortUrl.user_id == uid).all()
    
    if not short_url_obj:
        raise HTTPException(status_code=404, detail="User not found")

    stats = []
    for url in short_url_obj:
        visits_obj = db.query(Visit).filter(Visit.short_url_id == url.id).order_by(Visit.visit_time.desc())
        if visits_obj.count() == 0:
            stats.append({"long_url": url.long_url, "visits": url.visits, "recent visits":[]})
        else:
            stats.append({"long_url": url.long_url, "visits": url.visits, "recent visits": visits_obj.all()})

    return stats

#temporary to check for above logic's ability
@app.get("/url/stats")
def get_stats(db: Session = Depends(get_db)):
    short_url_obj = db.query(ShortUrl).filter(ShortUrl.user_id == None).all()

    if not short_url_obj:
        return {"urls": []}

    stats = []
    for url in short_url_obj:
        visits_obj = db.query(Visit).filter(Visit.short_url_id == url.id).order_by(Visit.visit_time.desc())
        stats.append({
            "short_url": url.short_url,
            "long_url": url.long_url, 
            "visits": url.visits, 
            "recent_visits": visits_obj.all()
        })

    return {"urls": stats}


# Background job to sync Redis visit counters to DB
# This will run every 5 minutes to ensure Redis and DB are in sync.
scheduler = BackgroundScheduler()
@scheduler.scheduled_job('interval', minutes=5)
def scheduled_sync_visits_to_db():
    """Background job: open a DB session and sync Redis visit counters to DB."""
    db = SessionLocal()
    try:
        # Use the helper's implementation to avoid duplication.
        sync_visits_to_db(db)
    finally:
        db.close()

# Start scheduler when this module is imported by Uvicorn.
scheduler.start()