import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
# Prefer DATABASE_URL from environment (set by docker-compose), fallback to local default
SQLALCHEMY_DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'postgresql+psycopg://postgres:postgres@localhost:5432/short_url'
)

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()