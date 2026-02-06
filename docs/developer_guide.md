# MedShield Developer Guide

## Setup

### Prerequisites

- Python 3.9+
- pip (Python package manager)
- Ollama (optional, for local LLM)
- Git

### Installation

1. **Clone the repository:**
```bash
git clone <repository-url>
cd medshield
```

2. **Install dependencies:**
```bash
cd backend
pip install -r requirements.txt
```

3. **Configure environment:**
```bash
# Copy example config
cp config.example.py ../.env

# Edit .env with your API keys
# Required: GROQ_API_KEY, PINECONE_API_KEY
# Optional: OLLAMA_HOST, OPENAI_API_KEY
```

4. **Run tests to verify setup:**
```bash
cd backend
python -m pytest tests/ -v
```

5. **Start the server:**
```bash
cd backend
uvicorn main:app --reload
```

---

## Project Structure

```
medshield/
├── backend/
│   ├── agents/                    # Core agent logic
│   │   ├── coordinator.py         # Main orchestrator
│   │   ├── gatekeeper.py          # Privacy agent (PII anonymization)
│   │   ├── session_manager.py     # Session state machine
│   │   ├── context_agent.py       # Context storage & retrieval
│   │   ├── execution_agent.py     # Task execution (appointments, etc.)
│   │   ├── worker.py              # Cloud worker (Groq API)
│   │   ├── hitl_manager.py        # Human-in-the-loop confirmations
│   │   └── memory_manager.py      # Short/long-term memory
│   ├── database/                  # Data persistence
│   │   ├── models.py              # SQLAlchemy models
│   │   └── identity_vault.py      # Patient registry & identity vault
│   ├── routes/                    # API endpoints
│   │   ├── chat.py                # Unified chat endpoint
│   │   ├── appointments.py        # Appointment scheduling
│   │   ├── followups.py           # Follow-up scheduling
│   │   └── summaries.py           # Summary generation
│   ├── vector_store/              # Vector storage (Pinecone / mock)
│   │   ├── semantic_store.py      # Pinecone semantic store
│   │   ├── mock_semantic_store.py # Mock for testing
│   │   ├── metadata_store.py      # Patient metadata vectors
│   │   └── mock_stores.py         # Mock vector stores
│   ├── rag/                       # RAG pipeline
│   │   ├── embeddings.py          # Embedding generation
│   │   ├── retriever.py           # Context retrieval
│   │   └── synthetic_data.py      # Synthetic data loader
│   ├── utils/                     # Utilities
│   │   ├── config.py              # Configuration (pydantic-settings)
│   │   ├── pii_patterns.py        # PII detection regex patterns
│   │   └── validators.py          # Input validators
│   ├── tests/                     # Test suites
│   │   ├── conftest.py            # Pytest fixtures
│   │   ├── test_e2e_workflow.py   # End-to-end tests
│   │   ├── test_integration.py    # Component integration tests
│   │   ├── test_performance.py    # Performance benchmarks
│   │   ├── test_privacy_compliance.py  # Privacy verification
│   │   ├── test_chat_interface.py # Chat interface tests
│   │   └── ...                    # Additional test files
│   ├── main.py                    # FastAPI application entry point
│   └── manual_test.py             # Manual E2E test script
├── frontend/
│   ├── templates/
│   │   └── index.html             # Unified chat interface
│   └── static/
│       ├── css/
│       │   └── chatbot.css        # Chat-specific styles
│       └── js/
│           ├── chat.js            # Chat logic
│           └── main.js            # Utilities
├── synthetic_data/                # Synthetic medical data
│   ├── doctors.json               # Doctor profiles
│   ├── medical_knowledge.json     # Medical knowledge base
│   ├── hospital_policies.json     # Hospital policies
│   └── appointment_rules.json     # Appointment rules
├── docs/                          # Documentation
│   ├── architecture.md            # System architecture
│   ├── api_documentation.md       # API reference
│   ├── developer_guide.md         # This file
│   ├── deployment.md              # Deployment guide
│   └── privacy_compliance.md      # Privacy documentation
└── config.example.py              # Example configuration
```

---

## Architecture Overview

MedShield follows a **multi-agent architecture** with privacy at its core:

```
User Message → Gatekeeper (Anonymize) → Coordinator → Context Agent → Execution Agent → Worker
                                                                                           ↓
User ← Gatekeeper (De-anonymize) ← Coordinator ← ──────────────────────────── Result ←────┘
```

### Key Components

1. **Gatekeeper**: Intercepts all data, detects and anonymizes PII before cloud services
2. **Coordinator**: Orchestrates multi-agent workflows, manages conversation state
3. **Session Manager**: SQLite-backed session state machine with workflow tracking
4. **Context Agent**: Stores/retrieves patient interactions with vector embeddings
5. **Execution Agent**: Handles appointment booking, follow-ups, and summaries
6. **HITL Manager**: Manages confirmations and clarifications without state resets
7. **Identity Vault**: Local-only PII storage with audit trail

---

## Adding New Features

### Adding a New Workflow

1. **Define intent detection** in `coordinator.py`:
```python
async def detect_intent(self, message: str) -> str:
    if 'new_keyword' in message.lower():
        return "new_workflow"
```

2. **Add workflow handler** in `coordinator.py`:
```python
async def _continue_new_workflow(self, session_id, session, message, stage):
    # Handle each stage
    pass
```

3. **Add execution logic** in `execution_agent.py`:
```python
async def handle_new_task(self, patient_uuid, data):
    # Execute the task
    pass
```

4. **Write tests** in `tests/test_new_workflow.py`

5. **Update documentation**

### Modifying Privacy Rules

1. Edit PII patterns in `utils/pii_patterns.py`
2. Update Gatekeeper detection in `agents/gatekeeper.py`
3. Add tests in `tests/test_gatekeeper_privacy.py`
4. Verify with `tests/test_privacy_compliance.py`

---

## Testing Strategy

| Layer | Files | Purpose |
|-------|-------|---------|
| Unit | `test_agents.py`, `test_gatekeeper.py` | Individual component testing |
| Integration | `test_integration.py`, `test_coordinator.py` | Component interaction testing |
| E2E | `test_e2e_workflow.py` | Full user journey testing |
| Performance | `test_performance.py` | Response time and scalability |
| Privacy | `test_privacy_compliance.py` | Privacy guarantee verification |
| API | `test_api_routes.py`, `test_chat_interface.py` | Endpoint testing |

### Running Tests

```bash
cd backend

# All tests
python -m pytest tests/ -v

# Specific test file
python -m pytest tests/test_e2e_workflow.py -v

# With coverage
python -m pytest tests/ --cov=agents --cov=routes --cov-report=html

# Performance tests
python -m pytest tests/test_performance.py -v
```

---

## Common Tasks

### Adding a New API Endpoint

1. Create route in `routes/` directory
2. Add router to `main.py`
3. Write tests in `tests/`
4. Update API documentation

### Debugging

```bash
# Run with debug logging
LOG_LEVEL=DEBUG uvicorn main:app --reload

# Run specific test with output
python -m pytest tests/test_specific.py -v -s

# Manual testing
python manual_test.py
```

### Database Operations

```python
from database.identity_vault import identity_vault

# Create patient
uuid, is_new = identity_vault.pseudonymize_patient("John Doe", age=30, gender="Male")

# Lookup patient
identity = identity_vault.reidentify_patient(uuid)

# Get audit trail
logs = identity_vault.get_audit_logs(patient_uuid=uuid)
```
