import time
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import datasets, export, pipelines
from app.core.config import settings
from app.core.db import Base, engine
from app.models import entities  # noqa: F401  (registrasi tabel)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="CSV2Trust API", version="1.0.0", lifespan=lifespan,
              description="From Messy Spreadsheet to Trusted Data Pipeline.")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])

_hits: dict[str, list[float]] = defaultdict(list)


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    ip, now = (request.client.host if request.client else "unknown"), time.time()
    _hits[ip] = [t for t in _hits[ip] if now - t < 60]
    if len(_hits[ip]) >= settings.rate_limit_per_min:
        return JSONResponse({"detail": "Terlalu banyak permintaan. Coba lagi sebentar lagi."}, status_code=429)
    _hits[ip].append(now)
    return await call_next(request)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    return JSONResponse({"detail": "Terjadi kesalahan di server saat memproses permintaan."}, status_code=500)


@app.get("/api/health", tags=["system"])
def health():
    return {"status": "ok", "llm_provider": settings.llm_provider}


for r in (datasets.router, pipelines.router, export.router):
    app.include_router(r)
