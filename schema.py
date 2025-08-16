from pydantic import BaseModel, HttpUrl
from datetime import datetime
from typing import Optional

class CreateShortUrl(BaseModel):
    user_id: Optional[str] = None
    url: HttpUrl
    custom_alias: Optional[str] = None

class ShortUrlResponse(BaseModel):
    id: int
    short_url: str
    long_url: str
    visits: int
    created_at: datetime

class ShortUrlStats(BaseModel):
    id: int
    short_url: str
    long_url: str
    visits: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None
