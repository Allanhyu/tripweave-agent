"""FastAPI entrypoint for TripWeave Agent."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.runtime_settings import load_backend_env


def _cors_origins() -> list[str]:
    configured = load_backend_env().get("CORS_ORIGINS", "")
    if configured.strip():
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return ["http://127.0.0.1:5190", "http://localhost:5190"]


app = FastAPI(
    title="TripWeave Agent API",
    version="1.0.0",
    description="A framework-free Agent core and travel-planning API.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
