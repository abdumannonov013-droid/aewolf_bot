from fastapi import FastAPI
from app.config import settings

app = FastAPI(title="Zyx Media API", version="1.0.0")

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "zyx-media-api",
        "environment": settings.environment,
    }
