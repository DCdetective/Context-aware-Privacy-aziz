"""
MedShield Configuration Example (Prompt 12)

Copy this file to create a .env file in the project root:
    cp config.example.py ../.env

Then fill in the actual values.
"""

# ── Database ──────────────────────────────────────────────────────────
DATABASE_URL = "sqlite:///./database/identity_vault.db"

# ── Pinecone (Vector Store) ──────────────────────────────────────────
PINECONE_API_KEY = "your-pinecone-api-key-here"
PINECONE_ENVIRONMENT = "us-east-1"
PINECONE_INDEX_METADATA = "medshield-metadata"
PINECONE_INDEX_SYNTHETIC = "medshield-synthetic"

# ── Groq (Cloud LLM) ────────────────────────────────────────────────
GROQ_API_KEY = "your-groq-api-key-here"

# ── Local LLM (Ollama – Optional) ───────────────────────────────────
# Used by the Gatekeeper for local PII extraction.
# If unavailable, regex fallback is used automatically.
OLLAMA_HOST = "http://localhost:11434"
OLLAMA_MODEL = "llama3.1"
LOCAL_LLM_ENABLED = False

# ── OpenAI (Embeddings – Optional) ──────────────────────────────────
OPENAI_API_KEY = "your-openai-api-key-here"

# ── Server ───────────────────────────────────────────────────────────
BACKEND_HOST = "0.0.0.0"
BACKEND_PORT = 8000
FRONTEND_URL = "http://localhost:8000"

# ── Logging ──────────────────────────────────────────────────────────
LOG_LEVEL = "INFO"

# ── Testing ──────────────────────────────────────────────────────────
TESTING_MODE = False

# ── Security ─────────────────────────────────────────────────────────
SECRET_KEY = "change-this-in-production"

# ── Privacy ──────────────────────────────────────────────────────────
MAX_PII_LOG_RETENTION_DAYS = 30
PRIVACY_AUDIT_ENABLED = True

# ── Performance ──────────────────────────────────────────────────────
MAX_CONCURRENT_SESSIONS = 100
SESSION_TIMEOUT_MINUTES = 30
