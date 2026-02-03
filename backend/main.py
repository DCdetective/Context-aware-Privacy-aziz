from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import logging

from utils.config import settings
from database.identity_vault import identity_vault

# Import routes
from routes.appointments import router as appointments_router
from routes.followups import router as followups_router
from routes.summaries import router as summaries_router

# Import semantic store based on mode
if settings.testing_mode:
    from vector_store.mock_semantic_store import MockSemanticStore
    semantic_store = MockSemanticStore()
else:
    from vector_store.semantic_store import semantic_store

# Import agents and inject dependencies
from agents.gatekeeper import gatekeeper_agent
from agents.worker import worker_agent

# Inject semantic store into agents
gatekeeper_agent.semantic_store = semantic_store
worker_agent.semantic_store = semantic_store

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="MedShield v2 - Privacy-Preserving Medical Chatbot",
    description="Multi-agent conversational system ensuring PII never leaves the local environment",
    version="2.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(appointments_router)
app.include_router(followups_router)
app.include_router(summaries_router)

@app.on_event("startup")
async def startup_event():
    """Initialize system components on startup."""
    logger.info("=" * 60)
    logger.info("🏥 MedShield v2 - Privacy-Preserving Medical Chatbot")
    logger.info("=" * 60)
    logger.info("Initializing system components...")
    logger.info("✓ Configuration loaded")
    logger.info("✓ Logging configured")
    logger.info("=" * 60)
    logger.info("🚀 System Ready")
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
        "service": "MedShield v2",
        "version": "2.0.0"
    }

# Frontend page routes
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Serve the home page."""
    logger.info("Serving home page")
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/appointment", response_class=HTMLResponse)
async def appointment_page(request: Request):
    """Serve the appointment booking page."""
    logger.info("Serving appointment page")
    return templates.TemplateResponse("appointment.html", {"request": request})

@app.get("/followup", response_class=HTMLResponse)
async def followup_page(request: Request):
    """Serve the follow-up scheduling page."""
    logger.info("Serving follow-up page")
    return templates.TemplateResponse("followup.html", {"request": request})

@app.get("/summary", response_class=HTMLResponse)
async def summary_page(request: Request):
    """Serve the medical summary page."""
    logger.info("Serving summary page")
    return templates.TemplateResponse("summary.html", {"request": request})


if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting MedShield Backend on {settings.backend_host}:{settings.backend_port}")
    uvicorn.run(
        "main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=True
    )
