"""Standalone uvicorn server for running the Intentionally Flawed Demo Target API on port 8001."""
import os
import sys
import uvicorn
from fastapi import FastAPI

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.demo_target.routes import demo_target_router

demo_app = FastAPI(
    title="Alpha Commerce Flawed Target API",
    version="1.0.0",
    description="Stand-alone mock microservice for API Sentinel demonstrations.",
)

demo_app.include_router(demo_target_router)


if __name__ == "__main__":
    print("=" * 60)
    print("  Starting Alpha Commerce Demo Target API on http://127.0.0.1:8001")
    print("  OpenAPI Docs available at: http://127.0.0.1:8001/docs")
    print("=" * 60)
    uvicorn.run(demo_app, host="127.0.0.1", port=8001)
