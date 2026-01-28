from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import logging

from utils.config import settings
from database.identity_vault import identity_vault

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="MedShield - Privacy-Preserving Medical Assistant",
    description="A multi-agent system ensuring PII never leaves the local environment",
    version="1.0.0"
)

@app.on_event("startup")
async def startup_event():
    """Initialize system components on startup."""
    logger.info("=" * 60)
    logger.info("🏥 MedShield - Privacy-Preserving Medical Assistant")
    logger.info("=" * 60)
    logger.info("Initializing Local Identity Vault...")
    logger.info(f"Database path: {settings.sqlite_db_path}")
    logger.info("Identity Vault initialized successfully")
    logger.info("=" * 60)

# Mount static files
app.mount("/static", StaticFiles(directory="../frontend/static"), name="static")

# Setup templates
templates = Jinja2Templates(directory="../frontend/templates")

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint for system status."""
    return {
        "status": "healthy",
        "service": "MedShield Backend",
        "version": "1.0.0",
        "components": {
            "identity_vault": "operational"
        }
    }

# Root endpoint
@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the home page."""
    logger.info("Serving home page")
    return HTMLResponse(
        content="<h1>MedShield - Identity Vault Initialized</h1>",
        status_code=200
    )


if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting MedShield Backend on {settings.backend_host}:{settings.backend_port}")
    uvicorn.run(
        "main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=True
    )
