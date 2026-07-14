"""Development server launcher."""

import uvicorn

from app.runtime_settings import load_backend_env


if __name__ == "__main__":
    env = load_backend_env()
    uvicorn.run(
        "app.main:app",
        host=env.get("HOST", "127.0.0.1"),
        port=int(env.get("PORT", "8010")),
        reload=env.get("RELOAD", "false").lower() in {"1", "true", "yes", "on"},
    )
