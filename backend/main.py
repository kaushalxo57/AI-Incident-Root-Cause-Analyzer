import os
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.routes import health, logs, incidents, services, analytics

# Setup logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("backend.main")

# Initialize FastAPI App
app = FastAPI(
    title="AI Incident & Root-Cause Analyzer",
    description="A production-style log analysis and root-cause mapping dashboard.",
    version="1.0.0"
)

# Set CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(health.router)
app.include_router(logs.router)
app.include_router(incidents.router)
app.include_router(services.router)
app.include_router(analytics.router)


# Global Exception Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception during request {request.url.path}")
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please verify backend logs."}
    )


# Serve Static Files
# Check if directories exist
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
css_dir = os.path.join(frontend_dir, "css")
js_dir = os.path.join(frontend_dir, "js")

# Proactively create directories if they don't exist
os.makedirs(css_dir, exist_ok=True)
os.makedirs(js_dir, exist_ok=True)

# Mount CSS & JS subfolders
app.mount("/css", StaticFiles(directory=css_dir), name="css")
app.mount("/js", StaticFiles(directory=js_dir), name="js")


# Serve index.html at root
@app.get("/")
def serve_index():
    index_file = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return JSONResponse(
        status_code=404,
        content={"detail": "Frontend index.html not found. Please verify folder setup."}
    )
