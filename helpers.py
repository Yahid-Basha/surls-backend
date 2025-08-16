from models import ShortUrl, Visit
from sqlalchemy.orm import Session
from dotenv import load_dotenv
import os
import redis

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
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

def sync_visits_to_db(db: Session):
    # Find all visits:* keys
    for key in redis_client.keys("visits:*"):
        short_code = key.split(":")[1]
        visit_count = int(redis_client.get(key) or 0)

        # Update DB visits
        short_url_obj = db.query(ShortUrl).filter(ShortUrl.short_url == short_code).first()
        if short_url_obj:
            short_url_obj.visits = visit_count
            db.commit()

        # Optionally clear key
        redis_client.delete(key)
