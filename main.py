from __future__ import annotations

import os

import uvicorn
from dotenv import load_dotenv

from api.app import create_app


load_dotenv()

app = create_app(os.getenv("JARVIS_CONFIG", "config/default.yaml"))


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=os.getenv("JARVIS_HOST", "127.0.0.1"),
        port=int(os.getenv("JARVIS_PORT", "8765")),
        reload=os.getenv("JARVIS_RELOAD", "false").lower() == "true",
    )
