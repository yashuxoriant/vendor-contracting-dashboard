"""
FastAPI Main Application
Entry point for the IT BOM Creation System backend
"""

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
import logging
import time
import os
from typing import Dict, Any

from config import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    description="AI-powered BOM creation assistant and analytics dashboard",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)


@app.on_event("startup")
async def startup_event():
    """Eagerly connect to Cosmos DB and ADLS on boot so misconfiguration is caught early."""
    from db import get_cosmos_client, get_adls_client
    try:
        get_cosmos_client()
        logger.info("Cosmos DB: connected")
    except Exception as e:
        logger.warning(f"Cosmos DB unavailable at startup (will use mock or fail on request): {e}")
    try:
        get_adls_client()
        logger.info("ADLS: connected")
    except Exception as e:
        logger.warning(f"ADLS unavailable at startup (will use mock or fail on request): {e}")

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GZip Middleware (compress responses)
app.add_middleware(GZipMiddleware, minimum_size=1000)


# Request Timing Middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Add processing time to response headers"""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    logger.info(f"{request.method} {request.url.path} - {process_time:.4f}s")
    return response


# Exception Handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors"""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors(), "body": exc.body}
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all uncaught exceptions"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error. Please try again later."}
    )


# Health Check Endpoints
@app.get("/health", tags=["Health"])
async def health_check() -> Dict[str, Any]:
    """Basic health check"""
    return {
        "status": "healthy",
        "environment": settings.environment,
        "version": "1.0.0"
    }


@app.get("/health/ready", tags=["Health"])
async def readiness_check() -> Dict[str, Any]:
    """
    Readiness check - verifies all dependencies are ready
    TODO: Add checks for Cosmos DB, ADLS, Key Vault connectivity
    """
    checks = {
        "cosmos_db": "not_implemented",
        "adls": "not_implemented",
        "key_vault": "not_implemented",
        "anthropic_api": "not_implemented"
    }
    
    all_ready = all(check != "not_implemented" for check in checks.values())
    
    return {
        "status": "ready" if all_ready else "not_ready",
        "checks": checks
    }


@app.get("/", tags=["Root"])
async def root() -> Dict[str, str]:
    """Root endpoint"""
    return {
        "message": f"Welcome to {settings.app_name}",
        "docs": "/api/docs",
        "health": "/health"
    }


# Import and register API routers
from api import chat, bom, analytics, templates, audit, catalog, sharepoint, notify

app.include_router(chat.router)
app.include_router(bom.router)
app.include_router(analytics.router)
app.include_router(templates.router)
app.include_router(audit.router)
app.include_router(catalog.router)
app.include_router(sharepoint.router)
app.include_router(notify.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )

# ── Serve built React frontend (production / Docker) ─────────────────────────
# Static files are present when built via Docker multi-stage (Stage 1 copies
# frontend/dist → /app/static). In local dev this folder won't exist, so we
# skip mounting silently and rely on Vite dev server instead.
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(_static_dir, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        """Catch-all: return index.html for any non-API route (React SPA routing)."""
        index = os.path.join(_static_dir, "index.html")
        return FileResponse(index)
