from fastapi import FastAPI
from app import app as api_router
from auth import router as auth_router

app = FastAPI(title="URL Shortener API", version="1.0.0")

app.include_router(api_router)
app.include_router(auth_router, prefix="/api/auth")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
