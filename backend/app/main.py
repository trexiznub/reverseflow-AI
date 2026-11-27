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

import threading  # noqa: E402

from .bootstrap import ensure_ready, status as boot_status  # noqa: E402
from .routers import analytics, case, core, forecast, intel, ops, portals, sap  # noqa: E402


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Prepare the demo in the background so the server opens its port at once.
    # Hosts such as Render stop a service that takes too long to bind a port;
    # on a small instance the first-run data generation can take several minutes.
    threading.Thread(target=_prepare, name="bootstrap", daemon=True).start()
    yield


def _prepare():
    try:
        ensure_ready()
    except Exception:  # status() already records the error for the UI
        pass


app = FastAPI(title="REVERSEFLOW AI API", version="1.0.0", lifespan=lifespan,
              description="Agentic intelligence for fashion e-commerce returns. All data is synthetic demonstration data.")


@app.middleware("http")
async def wait_until_ready(request: Request, call_next):
    """While the demo is being prepared, answer API calls with 503 instead of failing on a half-built database."""
    path = request.url.path
    if path.startswith("/api/") and path not in ("/api/health",) and not boot_status()["ready"]:
        st = boot_status()
        return JSONResponse({"detail": "The demo is getting ready", "status": st}, status_code=503)
    return await call_next(request)


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


for r in (core.router, forecast.router, intel.router, ops.router, portals.router, analytics.router, case.router, sap.router):
    app.include_router(r, prefix="/api")
