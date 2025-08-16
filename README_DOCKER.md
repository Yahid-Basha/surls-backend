# URL Shortener – Containerized

This repo is set up to run with Docker and Docker Compose.

## Requirements

- Docker Desktop 4.0+
- macOS/Linux/Windows

## Services

- api: FastAPI app served by Uvicorn
- db: Postgres 16
- redis: Redis 7

## Quick start

```bash
# Build and start all services
docker compose up --build -d

# View logs
docker compose logs -f api

# Stop
docker compose down
```

App will be available at http://localhost:8000

## Configuration

Environment variables used by the app:

- DATABASE_URL (defaults in compose to postgresql://postgres:postgres@db:5432/short_url)
- REDIS_HOST (defaults in compose to redis)
- REDIS_PORT (defaults in compose to 6379)
- AWS_REGION / AWS_DEFAULT_REGION
- COGNITO_USER_POOL_ID
- COGNITO_CLIENT_ID
- COGNITO_CLIENT_SECRET (only if your app client is configured with a secret)

For local (non-Docker), copy `.env.example` to `.env` and set values, then run `uvicorn main:app --reload`.

## Notes

- Database tables are auto-created via SQLAlchemy metadata at import time.
- A background scheduler syncs Redis `visits:*` counters to Postgres every 5 minutes.
- Cognito auth endpoints are available under `/api/auth`:
  - POST `/api/auth/register` {username, password}
  - POST `/api/auth/confirm` {username, code}
  - POST `/api/auth/login` {username, password}
  - POST `/api/auth/refresh` {refresh_token}
  - POST `/api/auth/logout` (Authorization: Bearer <access token>)
  - GET `/api/auth/me` (Authorization: Bearer <access token>)
