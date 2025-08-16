import os
import string
import random
import requests
from helpers import sync_visits_to_db, update_visit_in_db
import redis
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
print(f"Connecting to Redis at {REDIS_HOST}:{REDIS_PORT}")
redis_client = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
if not redis_client.ping():
    print("Failed to connect to Redis")
    redis_client = None

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
    # Store in Redis
    redis_client.set(f"short:{short_url_obj.short_url}", short_url_obj.long_url)
    # Also init visits counter in Redis (set if not exists)
    redis_client.setnx(f"visits:{short_url_obj.short_url}", short_url_obj.visits or 0)
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

    # Cache miss
    short_url_obj = db.query(ShortUrl).filter(ShortUrl.short_url == short_url).first()
    if not short_url_obj:
        raise HTTPException(status_code=404, detail="URL not found")

    redis_client.set(f"short:{short_url}", short_url_obj.long_url)
    redis_client.set(f"visits:{short_url}", short_url_obj.visits or 0)
    redis_client.incr(f"visits:{short_url}")

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