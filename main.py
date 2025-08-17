from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app import app as api_router

app = FastAPI(title="URL Shortener API", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000", 
        "http://localhost:3000",   # React default
        "http://127.0.0.1:3000",
        "http://localhost:5173",   # Vite default
        "http://127.0.0.1:5173",
        "http://localhost:8080",   # Vue/other common port
        "http://127.0.0.1:8080",
        # Add your production domains here when deploying
        # "https://yourdomain.com",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"],
    allow_headers=[
        "Authorization",
        "Content-Type", 
        "Accept",
        "Origin",
        "X-Requested-With",
        "Access-Control-Request-Method",
        "Access-Control-Request-Headers",
    ],
)

app.include_router(api_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)