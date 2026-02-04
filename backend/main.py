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
from routes.chat import router as chat_router

# Import semantic store based on mode
if settings.testing_mode:
    from vector_store.mock_semantic_store import MockSemanticStore
    semantic_store = MockSemanticStore()
else:
    from vector_store.semantic_store import semantic_store

# Import vector stores
from vector_store import metadata_store, synthetic_store
from vector_store.mock_stores import MockMetadataStore, MockSyntheticStore

# Import agents and inject dependencies
from agents.gatekeeper import gatekeeper_agent
from agents.worker import worker_agent
from agents.coordinator import coordinator_agent

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
app.include_router(chat_router)

@app.on_event("startup")
async def startup_event():
    """Initialize system components on startup."""
    logger.info("=" * 60)
    logger.info("🏥 MedShield v2 - Privacy-Preserving Medical Chatbot")
    logger.info("=" * 60)
    logger.info("Initializing system components...")
    logger.info("✓ Configuration loaded")
    logger.info("✓ Logging configured")
    
    # Initialize vector stores
    import vector_store.metadata_store as ms_module
    import vector_store.synthetic_store as ss_module
    
    if settings.testing_mode:
        ms_module.metadata_store = MockMetadataStore()
        ss_module.synthetic_store = MockSyntheticStore()
        logger.info("✓ Using mock vector stores (testing mode)")
    else:
        try:
            from vector_store.metadata_store import MetadataStore
            from vector_store.synthetic_store import SyntheticStore
            ms_module.metadata_store = MetadataStore()
            ss_module.synthetic_store = SyntheticStore()
            logger.info("✓ Pinecone vector stores initialized")
        except Exception as e:
            logger.warning(f"⚠ Failed to initialize Pinecone stores, using mocks: {e}")
            ms_module.metadata_store = MockMetadataStore()
            ss_module.synthetic_store = MockSyntheticStore()
            logger.info("✓ Using mock vector stores (fallback)")
    
    logger.info("=" * 60)
    logger.info("🚀 System Ready")
    logger.info("=" * 60)

# Resolve frontend paths robustly (do not rely on current working directory)
BACKEND_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = (BACKEND_DIR.parent / "frontend").resolve()
STATIC_DIR = (FRONTEND_DIR / "static").resolve()
TEMPLATES_DIR = (FRONTEND_DIR / "templates").resolve()

# Mount static files
# Note: StaticFiles checks existence at import time, so use absolute paths.
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Setup templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint for system status."""
    # Keep this lightweight and safe to call during tests (no external API calls).
    components = {
        "identity_vault": "operational" if identity_vault is not None else "down",
        "semantic_store": "operational" if semantic_store is not None else "down",
        "gatekeeper_agent": "operational" if gatekeeper_agent is not None else "down",
        "coordinator_agent": "operational" if coordinator_agent is not None else "down",
        "worker_agent": "operational" if worker_agent is not None else "down",
    }

    # Optional metric (some stores may not expose it)
    try:
        components["semantic_store_vectors"] = getattr(semantic_store, "vector_count", None)
    except Exception:
        components["semantic_store_vectors"] = None

    return {
        "status": "healthy",
        "service": "MedShield v2",
        "version": "2.0.0",
        "components": components,
    }

# Frontend page routes
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Serve the chatbot interface."""
    logger.info("Serving chatbot interface")
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
