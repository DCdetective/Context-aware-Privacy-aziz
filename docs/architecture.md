# MedShield System Architecture

## System Overview

MedShield is a **multi-agent, privacy-preserving medical assistant** that ensures no Personally Identifiable Information (PII) ever leaves the local environment while providing intelligent medical services through cloud LLMs.

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        MedShield Architecture                          │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  ┌─────────────┐    ┌──────────────┐    ┌───────────────┐              │
│  │   Frontend   │───▶│   FastAPI    │───▶│  Coordinator  │              │
│  │ (Chat UI)    │◀───│   Routes     │◀───│   Agent       │              │
│  └─────────────┘    └──────────────┘    └───────┬───────┘              │
│                                                  │                      │
│                            ┌─────────────────────┼─────────────────┐   │
│                            ▼                     ▼                 ▼   │
│                    ┌──────────────┐    ┌──────────────┐   ┌────────┐  │
│                    │  Gatekeeper  │    │   Context     │   │  HITL  │  │
│                    │  (Privacy)   │    │   Agent       │   │Manager │  │
│                    └──────┬───────┘    └──────┬───────┘   └────────┘  │
│                           │                   │                        │
│            LOCAL BOUNDARY  │                   │                        │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│─ ─ ─ ─ ─ ─ ─ ─ ─│─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │
│            CLOUD BOUNDARY  │                   │                        │
│                           ▼                   ▼                        │
│                    ┌──────────────┐    ┌──────────────┐                │
│                    │  Groq LLM   │    │  Pinecone    │                │
│                    │ (UUID only)  │    │ (Vectors)    │                │
│                    └──────────────┘    └──────────────┘                │
│                                                                        │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │                    LOCAL STORAGE                                │    │
│  │  ┌────────────┐  ┌────────────┐  ┌──────────────────────────┐ │    │
│  │  │  Identity   │  │  Session   │  │  Patient Registry       │ │    │
│  │  │  Vault      │  │  Manager   │  │  (SQLite)               │ │    │
│  │  │  (PII)      │  │  (State)   │  │                          │ │    │
│  │  └────────────┘  └────────────┘  └──────────────────────────┘ │    │
│  └────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Frontend (Unified Chat Interface)
- **Purpose**: Single ChatGPT-like conversational interface
- **Technology**: HTML, CSS, JavaScript
- **Features**: Chat messages, privacy sidebar, typing indicator
- **Location**: `frontend/templates/index.html`, `frontend/static/`

### 2. API Layer (FastAPI)
- **Purpose**: RESTful API endpoints
- **Routes**:
  - `/api/chat/message` – Unified chat endpoint
  - `/api/appointments/schedule` – Direct appointment booking
  - `/api/followups/schedule` – Follow-up scheduling
  - `/api/summaries/generate` – Summary generation
  - `/health` – System health check
- **Location**: `backend/routes/`

### 3. Coordinator Agent
- **Purpose**: Orchestrates multi-agent workflow
- **Key Feature**: Intent detection only when no active workflow (prevents state resets)
- **State Machine**: Manages workflow stages (resolving_patient → collecting_info → confirmation → completed)
- **Location**: `backend/agents/coordinator.py`

### 4. Gatekeeper (Privacy Agent)
- **Purpose**: PII anonymization and de-anonymization
- **Methods**: Local LLM (Ollama) + regex fallback
- **Guarantees**: No PII ever reaches cloud services
- **Transformations**: Names → UUIDs, Ages → Buckets, Phones → Masked
- **Location**: `backend/agents/gatekeeper.py`

### 5. Session Manager
- **Purpose**: Persistent conversation state tracking
- **Database**: SQLite (sessions.db)
- **State Machine**: Tracks active workflow, stage, patient, and workflow data
- **Location**: `backend/agents/session_manager.py`

### 6. Context Agent
- **Purpose**: Store and retrieve patient interactions using vector embeddings
- **Storage**: In-memory (testing) or Pinecone (production)
- **Features**: Semantic search, patient history, interaction filtering
- **Location**: `backend/agents/context_agent.py`

### 7. Execution Agent
- **Purpose**: Handle appointment booking, follow-ups, and summaries
- **Features**: Date/time parsing, specialty validation, doctor assignment
- **Location**: `backend/agents/execution_agent.py`

### 8. HITL Manager
- **Purpose**: Human-in-the-loop confirmations and clarifications
- **Key Feature**: Never resets conversation state during HITL
- **Location**: `backend/agents/hitl_manager.py`

### 9. Identity Vault
- **Purpose**: Local-only PII storage with UUID ↔ Name mapping
- **Database**: SQLite (identity_vault.db)
- **Features**: Pseudonymization, re-identification, audit trail
- **Location**: `backend/database/identity_vault.py`

### 10. Memory Manager
- **Purpose**: Short-term (session) and long-term (database) memory
- **Location**: `backend/agents/memory_manager.py`

## Data Flow

### Complete Workflow Example: Appointment Scheduling

```
1. User: "Book appointment for Aziz, 21, male, chest pain"
   │
2. ▼ FastAPI Route (/api/chat/message)
   │
3. ▼ Gatekeeper Agent
   │  - Detect PII: "Aziz" (name), "21" (age)
   │  - Pseudonymize: Aziz → UUID-abc123
   │  - Age bucket: 21 → "early 20s"
   │  - Extract intent: "appointment"
   │  - Extract semantics: {category: "cardiac", urgency: "routine"}
   │
4. ▼ Identity Vault (local)
   │  - Store: UUID-abc123 ↔ "Aziz", age=21, gender="male"
   │  - Log audit: pseudonymize_new, cloud_exposed=false
   │
5. ▼ Coordinator Agent
   │  - Check session state → no active workflow
   │  - Detect intent: "appointment"
   │  - Start workflow: appointment → resolving_patient
   │  - Resolve patient: find/create UUID
   │
6. ▼ Context Agent
   │  - Retrieve patient history (by UUID only)
   │  - RAG retrieval for relevant medical knowledge
   │  - Refine context with recommendations
   │
7. ▼ Execution Agent (or Worker via Groq)
   │  - Receives: UUID + semantic context (NO PII)
   │  - Schedule appointment
   │  - Assign doctor
   │  - Store record
   │
8. ▼ Gatekeeper Agent (re-identification)
   │  - UUID-abc123 → "Aziz"
   │  - Restore real name for display
   │
9. ▼ Response to User
      "Appointment booked for Aziz with Dr. Smith on Feb 13"
```

## Privacy Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    PRIVACY BOUNDARY                             │
│                                                                 │
│  LOCAL (PII allowed)          │  CLOUD (NO PII)                │
│  ─────────────────            │  ────────────────               │
│  • Identity Vault             │  • Groq LLM                    │
│  • Session Manager            │  • Pinecone Vectors            │
│  • Gatekeeper                 │  • Worker Agent                │
│  • Patient Registry           │                                 │
│  • Audit Logs                 │  Only receives:                │
│  • Medical Records            │  • Patient UUIDs               │
│                               │  • Semantic categories          │
│  Stores:                      │  • Age buckets                  │
│  • Real names                 │  • Anonymized text              │
│  • Exact ages                 │                                 │
│  • Phone numbers              │  NEVER receives:               │
│  • Addresses                  │  • Patient names                │
│  • SSNs                       │  • Exact ages                   │
│  • UUID ↔ PII mappings        │  • Phone numbers               │
│                               │  • Addresses                    │
└─────────────────────────────────────────────────────────────────┘
```

## Privacy Guarantees

1. **PII Never Leaves Local**: All personal information stays in local SQLite databases
2. **UUID-Only Cloud Communication**: Cloud services receive only anonymized UUIDs
3. **Semantic Extraction**: Medical context extracted without patient identifiers
4. **Audit Trail**: Every operation logged with privacy metadata
5. **Re-identification Only Local**: Patient names restored only for local display
6. **No PII in Logs**: System logs use UUIDs, not patient names

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python, FastAPI |
| Database | SQLite (local), SQLAlchemy ORM |
| Cloud LLM | Groq API (Llama 3.3 70B) |
| Local LLM | Ollama (Llama 3.1) |
| Vector Store | Pinecone (production), In-memory (testing) |
| Embeddings | Sentence Transformers |
| Frontend | HTML, CSS, JavaScript |
| Testing | pytest |
