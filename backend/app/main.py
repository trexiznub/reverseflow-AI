"""REVERSEFLOW AI: FastAPI application."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from .bootstrap import ensure_ready  # noqa: E402
from .routers import analytics, core, forecast, intel, ops, portals  # noqa: E402


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_ready()
    yield


app = FastAPI(title="REVERSEFLOW AI API", version="1.0.0", lifespan=lifespan,
              description="Agentic intelligence for fashion e-commerce returns. All data is synthetic demonstration data.")


@app.middleware("http")
async def errors_as_json(request: Request, call_next):
    """Turn unhandled errors into JSON *inside* the CORS layer so browsers can read them."""
    try:
        return await call_next(request)
    except Exception as exc:  # pragma: no cover
        logging.getLogger("reverseflow").exception("unhandled error on %s", request.url.path)
        return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})


# added last = outermost, so even error responses carry CORS headers
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(","),
                   allow_methods=["*"], allow_headers=["*"])


for r in (core.router, forecast.router, intel.router, ops.router, portals.router, analytics.router):
    app.include_router(r, prefix="/api")
