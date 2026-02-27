# MedShield v2 - Process Mechanism & System Architecture

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture: Three-Tier Privacy Model](#2-architecture-three-tier-privacy-model)
3. [Component Inventory](#3-component-inventory)
4. [Server Startup Sequence](#4-server-startup-sequence)
5. [Chat Pipeline: End-to-End Data Flow](#5-chat-pipeline-end-to-end-data-flow)
6. [API Route Pipelines (Appointments, Follow-ups, Summaries)](#6-api-route-pipelines)
7. [Agent Details](#7-agent-details)
8. [Privacy Enforcement Mechanisms](#8-privacy-enforcement-mechanisms)
9. [Database Schema & Identity Vault](#9-database-schema--identity-vault)
10. [Vector Stores & RAG Pipeline](#10-vector-stores--rag-pipeline)
11. [Session Management & State Machine](#11-session-management--state-machine)
12. [Human-in-the-Loop (HITL) Workflow](#12-human-in-the-loop-hitl-workflow)
13. [MCP Bridge: Model Context Protocol](#13-mcp-bridge-model-context-protocol)
14. [Frontend-Backend Communication](#14-frontend-backend-communication)
15. [Configuration & Environment](#15-configuration--environment)
16. [Testing](#16-testing)

---

## 1. System Overview

MedShield v2 is a **privacy-preserving medical chatbot** built on a multi-agent architecture. Its core guarantee is that **Personally Identifiable Information (PII) never leaves the local environment** -- all cloud processing operates exclusively on pseudonymised UUIDs and semantic features.

The system handles three primary use cases:
- **Appointment Booking** -- Schedule new doctor appointments
- **Follow-Up Scheduling** -- Schedule follow-up visits based on medical history
- **Medical Summary Generation** -- Produce comprehensive patient summaries

**Technology Stack:**
| Layer | Technology |
|-------|-----------|
| Backend Framework | FastAPI (Python) with Uvicorn |
| Local LLM | Ollama (configurable model, default `gemma3:1b`) |
| Cloud LLM | Groq API (`llama-3.3-70b-versatile`) |
| Local Database | SQLite via SQLAlchemy ORM |
| Vector Store | Pinecone (serverless, AWS) |
| Embeddings | Sentence Transformers (384-dimensional) |
| Frontend | Jinja2 templates with vanilla JS, served by FastAPI |

---

## 2. Architecture: Three-Tier Privacy Model

```
+-------------------------------------------------------------------+
|                       TIER 1: USER LAYER                          |
|   Browser (index.html, appointment.html, followup.html,          |
|            summary.html) + JavaScript (chat.js, main.js)          |
+-------------------------------------------------------------------+
        |  HTTP POST/GET  (JSON payloads contain raw PII)
        v
+-------------------------------------------------------------------+
|                 TIER 2: LOCAL PROCESSING LAYER                    |
|  (Everything below runs on the local machine -- PII stays here)  |
|                                                                   |
|  +------------------+   +-----------------+   +----------------+  |
|  | FastAPI Server   |   | Gatekeeper Agent|   | Identity Vault |  |
|  | (main.py)        |-->| (Ollama LLM)    |-->| (SQLite DB)    |  |
|  +------------------+   +-----------------+   +----------------+  |
|         |                       |                     |           |
|         |              PII stripped                    |           |
|         |              UUID + semantic context only    |           |
|         v                       v                     |           |
|  +------------------+   +-------------------+         |           |
|  | Session Manager  |   | MCP Bridge        |         |           |
|  | (in-memory)      |   | (privacy enforcer)|         |           |
|  +------------------+   +-------------------+         |           |
|         |                       | validates           |           |
|         |                       v                     |           |
+-------------------------------------------------------------------+
        |  Only UUIDs + semantic features cross this boundary
        v
+-------------------------------------------------------------------+
|                    TIER 3: CLOUD LAYER                            |
|                                                                   |
|  +--------------------+   +---------------------+                 |
|  | Context Agent      |   | Execution Agent     |                 |
|  | (Groq LLM + RAG)  |   | (Groq LLM)          |                 |
|  +--------------------+   +---------------------+                 |
|         |                        |                                |
|  +--------------------+   +---------------------+                 |
|  | Pinecone Metadata  |   | Pinecone Synthetic  |                 |
|  | Store (UUID-only)  |   | Store (hospital KB) |                 |
|  +--------------------+   +---------------------+                 |
+-------------------------------------------------------------------+
```

**Privacy Boundary Rule:** The dotted line between Tier 2 and Tier 3 is the privacy boundary. Data crossing this line must contain:
- Patient UUIDs (never real names)
- Semantic medical features (symptom category, urgency level)
- Age groups (never exact ages)
- No PII fields whatsoever

---

## 3. Component Inventory

### Backend Files (`backend/`)

| File | Class/Module | Role | Tier |
|------|-------------|------|------|
| `main.py` | FastAPI app | Server entry point, routing, startup | Local |
| `agents/gatekeeper.py` | `GatekeeperAgent` | PII extraction, pseudonymisation, re-identification | Local |
| `agents/coordinator.py` | `AgentCoordinator` | Full chat pipeline orchestration (10 steps) | Local |
| `agents/coordinator.py` | `CoordinatorAgent` | Task planning (Groq-based or rule fallback) | Cloud |
| `agents/context_agent.py` | `ContextRefinementAgent` | RAG-based context refinement (Groq) | Cloud |
| `agents/execution_agent.py` | `ExecutionAgent` | Task execution with RAG context (Groq) | Cloud |
| `agents/worker.py` | `WorkerAgent` | Deterministic task execution for API routes | Local |
| `agents/session_manager.py` | `SessionManager` | In-memory session & conversation tracking | Local |
| `agents/hitl_manager.py` | `HITLManager` | Multi-turn question generation & confirmation | Local |
| `agents/memory_manager.py` | `MemoryManager` | Short-term + long-term memory management | Local |
| `mcp/bridge.py` | `MCPBridge` | Privacy enforcement for all cloud data flows | Local |
| `database/identity_vault.py` | `IdentityVault` | SQLite PII storage, UUID mapping, audit trail | Local |
| `database/models.py` | SQLAlchemy models | `PatientIdentity`, `MedicalRecord`, `AuditLog` | Local |
| `rag/retriever.py` | `RAGRetriever` | Multi-source retrieval from Pinecone stores | Cloud |
| `rag/embeddings.py` | `EmbeddingGenerator` | Sentence Transformer embeddings (384-dim) | Local |
| `rag/synthetic_data.py` | `SyntheticDataLoader` | Hospital knowledge base loader | Local |
| `vector_store/metadata_store.py` | `MetadataStore` | Pinecone index for UUID-linked patient history | Cloud |
| `vector_store/synthetic_store.py` | `SyntheticStore` | Pinecone index for hospital knowledge base | Cloud |
| `vector_store/semantic_store.py` | `SemanticStore` | Semantic anchor storage | Cloud |
| `routes/chat.py` | FastAPI router | `/api/chat/message`, `/api/chat/privacy-report` | Local |
| `routes/appointments.py` | FastAPI router | `/api/appointments/schedule` | Local |
| `routes/followups.py` | FastAPI router | `/api/followups/schedule` | Local |
| `routes/summaries.py` | FastAPI router | `/api/summaries/generate` | Local |
| `utils/config.py` | `Settings` | Pydantic settings from `.env` file | Local |

### Frontend Files (`frontend/`)

| File | Role |
|------|------|
| `templates/index.html` | Three-panel chat dashboard (Nav, Chat, Process Monitor) |
| `templates/appointment.html` | Appointment booking form |
| `templates/followup.html` | Follow-up scheduling form |
| `templates/summary.html` | Medical summary generation form |
| `static/css/chatbot.css` | Dashboard styles (dark theme) |
| `static/css/styles.css` | Form page styles (dark theme) |
| `static/js/chat.js` | Chat logic, session management, pipeline visualisation |
| `static/js/main.js` | Shared navigation utilities |
| `static/js/appointment.js` | Appointment form submission logic |
| `static/js/followup.js` | Follow-up form submission logic |
| `static/js/summary.js` | Summary form submission logic |

---

## 4. Server Startup Sequence

**Entry point:** `backend/main.py` -- run via `cd backend && python main.py`

```
1. Import phase (synchronous):
   a. Load Settings from .env  (utils/config.py)
   b. Create IdentityVault singleton (SQLite DB created/opened)
   c. Import 4 route modules (chat, appointments, followups, summaries)
   d. Conditionally import SemanticStore or MockSemanticStore
   e. Import MockMetadataStore, MockSyntheticStore
   f. Import agent singletons: gatekeeper_agent, worker_agent, coordinator_agent
   g. Inject semantic_store into gatekeeper_agent and worker_agent

2. FastAPI app created:
   - Title: "MedShield v2 - Privacy-Preserving Medical Chatbot"
   - CORS middleware added (allow_origins=["*"])
   - 4 routers included (chat, appointments, followups, summaries)

3. Startup event (async, runs once when server starts):
   a. Import vector_store modules as module references
   b. If TESTING_MODE:
        - Assign MockMetadataStore() to metadata_store module attribute
        - Assign MockSyntheticStore() to synthetic_store module attribute
   c. Else (production):
        - Try: Create real MetadataStore() and SyntheticStore() (Pinecone)
        - Except: Fall back to mock stores
   d. Log "System Ready"

4. Static files mounted at /static -> frontend/static/
5. Jinja2 templates configured from frontend/templates/
6. Page routes registered: /, /appointment, /followup, /summary
7. Health endpoint registered: /health
8. Uvicorn starts on configured host:port (default 127.0.0.1:8000)
```

**Critical design note:** Vector stores are initialised as module-level `None` values (`metadata_store = None` in `vector_store/metadata_store.py`). The startup event assigns real instances to these module attributes. All consumer code imports the *module* (not the variable) so that attribute lookups happen at access time and see the updated values:

```python
# In coordinator.py, memory_manager.py, retriever.py:
import vector_store.metadata_store as _ms_mod
# Access via: _ms_mod.metadata_store (resolved at runtime)
```

---

## 5. Chat Pipeline: End-to-End Data Flow

The main chat pipeline is orchestrated by `AgentCoordinator.process_message()` in `backend/agents/coordinator.py`. This is the most complex flow in the system.

### Pipeline Steps

```
User types message in browser
        |
        v
[Frontend: chat.js]
  POST /api/chat/message  { message: "...", session_id: "..." }
        |
        v
[Route: routes/chat.py]
  Calls coordinator.process_message(message, session_id)
        |
        v
[AgentCoordinator.process_message()]

  Step 0: Session Setup
  ├── Create or retrieve session via SessionManager
  ├── Check for pending confirmations (HITL)
  ├── Check for pending disambiguations
  └── Check for question-gathering phase
        |
        v
  Step 1: Gatekeeper Processing  (LOCAL - Ollama LLM)
  ├── extract_pii(message)        -> {patient_name, age, gender, medical_info}
  ├── extract_intent(message)     -> "appointment" | "followup" | "summary" | "general"
  ├── extract_semantic_context()  -> {symptom_category, urgency_level, ...}
  └── create_privacy_report()     -> transformation details for frontend
        |
        v
  Step 2: Identity Resolution  (LOCAL - SQLite)
  ├── identity_vault.resolve_patient_identity(name, age, gender)
  ├── If 0 matches: return "needs_confirmation" -> ask user to confirm new patient
  ├── If 1 match:   return "resolved" -> set active patient in session
  └── If 2+ matches: return "needs_disambiguation" -> present candidates to user
        |
        v
  Step 3: Metadata Storage  (CLOUD - Pinecone)
  └── metadata_store.store_patient_metadata(uuid, semantic_context, intent)
      (Only UUID + semantic features stored; no PII crosses the boundary)
        |
        v
  Step 3.5: Memory Retrieval  (LOCAL + CLOUD)
  ├── memory_manager.get_patient_long_term_memory(uuid)
  │   ├── identity_vault.get_patient_records(uuid)     [LOCAL SQLite]
  │   └── metadata_store.retrieve_patient_history(uuid) [CLOUD Pinecone]
  ├── session_manager.get_conversation_context(session_id) [LOCAL in-memory]
  └── memory_manager.format_memory_for_llm(short_term, long_term)
        |
        v
  Step 4: MCP Bridge -> Context Agent  (CLOUD - Groq LLM)
  ├── mcp_bridge.route_to_cloud("context_agent", uuid, payload)
  │   └── Scans payload for PII fields/patterns, logs audit entry
  ├── context_agent.refine_context(uuid, intent, semantic_context, medical_info)
  │   ├── rag_retriever.retrieve_context_for_intent(uuid, intent, ...)
  │   │   ├── metadata_store.retrieve_patient_history(uuid)
  │   │   ├── synthetic_store.search_doctors(specialty)
  │   │   ├── synthetic_store.search_medical_knowledge(query)
  │   │   └── synthetic_store.search_similar_cases(query)
  │   ├── rag_retriever.format_context_for_llm(rag_context)
  │   └── Groq LLM call with RAG context -> refined recommendations
  └── mcp_bridge.route_from_cloud("context_agent", uuid, response)
      └── Scans response for PII, logs audit entry
        |
        v
  Step 5: MCP Bridge -> Execution Agent  (CLOUD - Groq LLM)
  ├── mcp_bridge.route_to_cloud("execution_agent", uuid, payload)
  ├── execution_agent.execute_task(uuid, intent, refined_context)
  │   ├── intent == "appointment": _handle_appointment_with_rag()
  │   ├── intent == "followup":    _handle_followup_with_rag()
  │   ├── intent == "summary":     _handle_summary_with_rag()
  │   └── intent == "general":     _handle_general_query()
  └── mcp_bridge.route_from_cloud("execution_agent", uuid, response)
        |
        v
  Step 5.5: HITL Check (for appointment/followup intents)
  ├── hitl_manager.generate_medical_questions(intent, semantic_context)
  ├── session_manager.set_pending_action(session_id, intent, data, questions)
  └── Return first question to user (pipeline pauses here)
      ... user answers questions across multiple turns ...
      ... after all questions answered, confirmation summary shown ...
      ... user confirms or cancels ...
        |
        v
  Step 6: Re-identification  (LOCAL - SQLite)
  └── identity_vault.reidentify_patient(uuid) -> {patient_name, age, gender}
      (Patient name restored into the response for display)
        |
        v
  Step 7: Response Formatting
  ├── Attach privacy_report and mcp_compliance to response
  ├── Build workflow_steps list for frontend pipeline visualisation
  └── Add response to session conversation history
        |
        v
[Route: routes/chat.py]
  Build ChatResponse with:
  ├── privacy_details: {pii_detected, original_contains, pseudonymized_to, ...}
  ├── workflow_steps: list of pipeline step descriptions
  ├── session_id: for multi-turn continuity
  └── disambiguation_data: (if applicable)
        |
        v
[Frontend: chat.js]
  Display response, update pipeline visualisation, show privacy details
```

---

## 6. API Route Pipelines

The standalone API routes (`/api/appointments/schedule`, `/api/followups/schedule`, `/api/summaries/generate`) use a simpler pipeline than the chat flow. They use `CoordinatorAgent` (task planner) + `WorkerAgent` (deterministic executor) instead of the full `AgentCoordinator` orchestrator.

### Appointment Pipeline (`routes/appointments.py`)

```
POST /api/appointments/schedule
  Body: { patient_name, age, gender, symptoms }
        |
  Step 1: Format input string from request fields
  Step 2: gatekeeper_agent.pseudonymize_input(input_string)
          ├── Extract PII (Ollama or regex in test mode)
          ├── identity_vault.pseudonymize_patient(name, age, gender)
          └── Return {patient_uuid, semantic_context, intent}
  Step 3: _coordinator.coordinate_request(uuid, "appointment", semantic_context)
          ├── Try Groq LLM planning
          └── Fallback to deterministic rules: steps=["validate","schedule","confirm"]
  Step 4: mcp_bridge.route_to_cloud("worker_agent", uuid, payload)
          worker_agent.execute_task(uuid, "appointment", execution_plan, semantic_context)
          mcp_bridge.route_from_cloud("worker_agent", uuid, result)
  Step 5: gatekeeper_agent.reidentify_output(uuid, worker_result)
          └── identity_vault.reidentify_patient(uuid) -> attach patient_name
  Step 6: Return AppointmentResponse
```

### Follow-Up Pipeline (`routes/followups.py`)

```
POST /api/followups/schedule
  Body: { patient_name }
        |
  Step 1: Look up patient UUID by name in identity_vault (must exist)
  Step 2: Retrieve semantic context from semantic_store (if available)
  Step 3: _coordinator.coordinate_request(uuid, "followup", semantic_context)
  Step 4: MCP Bridge -> worker_agent.execute_task() -> MCP Bridge
  Step 5: gatekeeper_agent.reidentify_output(uuid, result)
  Step 6: Return FollowUpResponse
```

### Summary Pipeline (`routes/summaries.py`)

```
POST /api/summaries/generate
  Body: { patient_name }
        |
  Step 1: gatekeeper_agent.pseudonymize_input() -> get UUID
  Step 2: _coordinator.coordinate_request(uuid, "summary", semantic_context)
  Step 3: MCP Bridge -> worker_agent.execute_task() -> MCP Bridge
  Step 4: gatekeeper_agent.reidentify_output(uuid, result)
  Step 5: Return SummaryResponse
```

---

## 7. Agent Details

### 7.1 Gatekeeper Agent (`agents/gatekeeper.py`)

**Location:** Local only (Tier 2)
**LLM:** Ollama (local, configurable model)
**Singleton:** `gatekeeper_agent`

The Gatekeeper is the first and last agent to touch user data. It is the only agent with access to raw PII.

**Responsibilities:**
1. **PII Extraction** (`extract_pii`): Uses local Ollama LLM to parse natural language and extract `{patient_name, age, gender, medical_info}` as structured JSON.
2. **Intent Classification** (`extract_intent`): Classifies user message into `appointment`, `followup`, `summary`, or `general`.
3. **Semantic Context Extraction** (`extract_semantic_context`): Extracts non-PII medical features: `symptom_category`, `urgency_level`, `requires_specialist`, `estimated_duration`. Validates output to detect PII leakage.
4. **Privacy Report Creation** (`create_privacy_report`): Documents each transformation (name->UUID, age->age_group, etc.) for the frontend privacy sidebar.
5. **Pseudonymisation** (`pseudonymize_input`): Convenience method that runs extraction + UUID mapping in one call. Used by API routes.
6. **Re-identification** (`reidentify_output`): Looks up patient UUID in identity vault and reattaches `patient_name`, `patient_age`, `patient_gender` to the response.

**Age Group Masking:**
| Exact Age | Age Group |
|-----------|-----------|
| 0-12 | child |
| 13-17 | teenager |
| 18-24 | early 20s |
| 25-34 | late 20s to early 30s |
| 35-44 | late 30s to early 40s |
| 45-54 | late 40s to early 50s |
| 55-64 | late 50s to early 60s |
| 65+ | senior |

**Fallback:** If Ollama is unavailable, `_fallback_semantic_extraction()` uses keyword matching to determine symptom category and urgency.

### 7.2 Agent Coordinator (`agents/coordinator.py` -- `AgentCoordinator`)

**Location:** Local orchestrator (Tier 2)
**Singleton:** `coordinator` (aliased as `coordinator_agent`)

This is the main pipeline orchestrator for the chat flow. It does NOT call any cloud LLM itself -- it coordinates the other agents.

**Key methods:**
- `process_message(user_message, session_id)` -- The main 10-step pipeline (see Section 5)
- `_finalize_appointment(uuid, action_data)` -- Stores appointment record after HITL confirmation
- `_finalize_followup(uuid, action_data)` -- Stores follow-up record after HITL confirmation
- `_extract_uuid_from_message(message)` -- Parses UUID or 8-char prefix from user input
- `_base_response(**overrides)` -- Template for all response dicts (ensures required keys)

**State handling:** The coordinator checks session state before starting the pipeline:
1. If `awaiting_confirmation` -- parse yes/no, execute or cancel
2. If questions pending -- collect next answer, or move to confirmation
3. If disambiguation pending -- parse UUID selection
4. Otherwise -- run full pipeline from Step 1

### 7.3 Coordinator Agent (`agents/coordinator.py` -- `CoordinatorAgent`)

**Location:** Cloud (Tier 3) with local fallback
**LLM:** Groq API (`llama-3.3-70b-versatile`)
**Singleton:** Instantiated per-route as `_coordinator` in each route file

A lightweight task planner used by the standalone API routes. Does NOT orchestrate the full pipeline.

**Planning modes:**
1. **Groq-based planning** (`_groq_execution_plan`): Sends UUID + semantic context to Groq, receives JSON execution plan with `steps`, `priority`, `requires_specialist`, `estimated_time`.
2. **Rule-based fallback** (`_fallback_execution_plan`): Deterministic planning when Groq is unavailable:
   - Appointment: `["validate", "schedule", "confirm"]`, 3 min
   - Follow-up: `["retrieve", "schedule", "confirm"]`, 2 min
   - Summary: `["gather", "generate", "format"]`, 2 min

### 7.4 Context Refinement Agent (`agents/context_agent.py`)

**Location:** Cloud (Tier 3)
**LLM:** Groq API (`llama-3.3-70b-versatile`)
**Singleton:** `context_agent`

Receives UUID + semantic context (no PII). Uses RAG retrieval to enrich context, then calls Groq LLM to produce refined recommendations.

**Output:** JSON with `recommended_specialty`, `recommended_doctor`, `urgency_assessment`, `estimated_duration`, `requires_follow_up`, `considers_history`, `reasoning`, and `rag_context` metadata.

**RAG integration:** Calls `rag_retriever.retrieve_context_for_intent()` which queries:
1. Patient history from metadata store (UUID-filtered)
2. Relevant doctors from synthetic store (specialty-filtered)
3. Medical knowledge from synthetic store (semantic search)
4. Similar cases from synthetic store (semantic search)

### 7.5 Execution Agent (`agents/execution_agent.py`)

**Location:** Cloud (Tier 3)
**LLM:** Groq API (`llama-3.3-70b-versatile`)
**Singleton:** `execution_agent`

Receives UUID + refined context from the Context Agent. Executes intent-specific handlers:

| Intent | Handler | Actions |
|--------|---------|---------|
| `appointment` | `_handle_appointment_with_rag()` | LLM recommends doctor, time, duration; stores medical record |
| `followup` | `_handle_followup_with_rag()` | LLM suggests timeline using history; stores record |
| `summary` | `_handle_summary_with_rag()` | LLM generates UUID-based summary; stores record |
| `general` | `_handle_general_query()` | Returns suggestions without LLM call |

Each RAG handler includes a fallback to the non-RAG version if the Groq call fails.

### 7.6 Worker Agent (`agents/worker.py`)

**Location:** Local (Tier 2)
**Singleton:** `worker_agent`

Deterministic task executor used by the standalone API routes (not the chat pipeline). Receives an execution plan from `CoordinatorAgent` and executes it without LLM calls.

### 7.7 Session Manager (`agents/session_manager.py`)

**Location:** Local (Tier 2) -- in-memory dictionary
**Singleton:** `session_manager`

Tracks per-session state:
- `active_patient_uuid` / `patient_name`
- `conversation_history` (list of `{role, message, timestamp}`)
- `pending_action` (HITL workflow state)
- `pending_disambiguation` (multiple patient matches)
- `created_at` / `last_activity` (30-minute timeout)

### 7.8 HITL Manager (`agents/hitl_manager.py`)

**Location:** Local (Tier 2)
**Singleton:** `hitl_manager`

Generates 2-3 context-specific medical questions before appointment/follow-up booking. Questions are tailored by `symptom_category`:
- Respiratory: breathing difficulty, contact history
- Cardiac: chest pain, heart condition history
- Neurological: vision changes, head injuries
- Digestive: nausea, dietary changes
- General: discomfort rating, medication history

Also creates confirmation summaries and parses yes/no responses.

### 7.9 Memory Manager (`agents/memory_manager.py`)

**Location:** Local (Tier 2)
**Singleton:** `memory_manager`

Combines two memory sources:
1. **Short-term:** Session conversation history (from `SessionManager`)
2. **Long-term:** Medical records from SQLite + interaction history from Pinecone metadata store

**Key methods:**
- `get_patient_long_term_memory(uuid)` -- Retrieves DB records + vector store history
- `format_memory_for_llm(short_term, long_term)` -- Formats combined memory for LLM prompt injection
- `detect_context_switch(message, active_patient_name)` -- Detects when user switches to a different patient using keyword triggers and name heuristics
- `clear_patient_memory(uuid)` -- GDPR right-to-deletion support

---

## 8. Privacy Enforcement Mechanisms

### 8.1 Pseudonymisation (Identity Vault)

Every patient name is mapped to a UUID v4 on first encounter:

```
"John Doe" -> identity_vault.pseudonymize_patient("John Doe", age=35, gender="Male")
           -> ("a3b7c9d1-e5f6-4a2b-8c3d-1e2f3a4b5c6d", True)
```

The UUID is the **only** identifier that crosses the privacy boundary.

### 8.2 Age Group Masking

Exact ages are converted to broad groups (see Section 7.1) before any cloud processing.

### 8.3 Semantic Extraction

Medical information is decomposed into non-identifying semantic features:
```
"I've been having severe headaches and dizziness for 3 days"
    -> {symptom_category: "neurological", urgency_level: "urgent",
        requires_specialist: true, estimated_duration: 30}
```

### 8.4 MCP Bridge Validation

Every payload crossing the privacy boundary is scanned by `MCPBridge` (see Section 13). Both outgoing and incoming payloads are validated.

### 8.5 Gatekeeper PII Leak Detection

After semantic extraction, the Gatekeeper checks the output for PII keywords (`name`, `age`, `years old`) and falls back to rule-based extraction if detected.

### 8.6 Audit Trail

Every identity vault operation is logged in the `audit_logs` table with:
- `operation`: what was done (pseudonymize, reidentify, store_record, etc.)
- `component`: which agent performed the operation
- `pii_accessed`: whether PII was touched
- `cloud_exposed`: whether data was sent to cloud (should always be `False`)

---

## 9. Database Schema & Identity Vault

### SQLite Database Location

`backend/database/identity_vault.db` (created automatically on startup)

Path resolution handles multiple working directories:
1. If `SQLITE_DB_PATH` is absolute -> use as-is
2. If relative and parent directory exists from CWD -> resolve normally
3. Otherwise -> fall back to the canonical directory next to `identity_vault.py`

### Tables

#### `patient_identities`

| Column | Type | Description |
|--------|------|-------------|
| `patient_uuid` | String(36), PK | UUID v4 identifier |
| `patient_name` | String(255), indexed | Real patient name (PII) |
| `age` | Integer, nullable | Patient age (PII) |
| `gender` | String(50), nullable | Patient gender |
| `created_at` | DateTime | Record creation time |
| `updated_at` | DateTime | Last update time |
| `last_accessed` | DateTime | Last access time |
| `access_count` | Integer | Number of times accessed |

#### `medical_records`

| Column | Type | Description |
|--------|------|-------------|
| `record_id` | String(36), PK | UUID v4 record identifier |
| `patient_uuid` | String(36), FK | Reference to patient |
| `record_type` | String(50) | "appointment", "followup", or "summary" |
| `symptoms` | Text, nullable | Patient symptoms |
| `diagnosis` | Text, nullable | Diagnosis text |
| `treatment_plan` | Text, nullable | Treatment plan |
| `notes` | Text, nullable | Additional notes |
| `created_at` | DateTime | Record creation time |

#### `audit_logs`

| Column | Type | Description |
|--------|------|-------------|
| `log_id` | String(36), PK | UUID v4 log identifier |
| `patient_uuid` | String(36), FK | Reference to patient |
| `operation` | String(100) | Operation performed |
| `component` | String(100) | Component name |
| `pii_accessed` | Boolean | Whether PII was accessed |
| `cloud_exposed` | Boolean | Whether data was exposed to cloud |
| `timestamp` | DateTime | Operation timestamp |
| `details` | Text, nullable | Additional details |

### Identity Vault Operations

| Method | Description |
|--------|-------------|
| `pseudonymize_patient(name, age, gender)` | Create or retrieve UUID for patient |
| `reidentify_patient(uuid)` | Get PII from UUID |
| `store_medical_record(uuid, type, symptoms, ...)` | Store medical record |
| `get_patient_records(uuid, type)` | Retrieve patient records |
| `resolve_patient_identity(name, age, gender)` | Collision-aware identity resolution |
| `confirm_new_patient(name, age, gender)` | Create patient after user confirmation |
| `find_patients_by_name(name)` | Search patients (case-insensitive LIKE) |
| `get_audit_logs(uuid, operation, limit)` | Retrieve audit trail |
| `verify_privacy_compliance()` | Check for cloud exposure violations |

---

## 10. Vector Stores & RAG Pipeline

### 10.1 Metadata Store (Pinecone)

**Index name:** `medshield-metadata` (configurable)
**Purpose:** Store UUID-linked semantic interaction history

**Privacy guarantee:** Stores ONLY:
- `patient_uuid` -- pseudonymised identifier
- `intent` -- appointment/followup/summary
- `symptom_category` -- general medical category
- `urgency_level` -- routine/urgent/emergency
- `requires_specialist` -- boolean
- `estimated_duration` -- minutes
- `timestamp` -- interaction time

**NO** patient names, exact ages, or identifying information.

### 10.2 Synthetic Store (Pinecone)

**Index name:** `medshield-synthetic` (configurable)
**Purpose:** Hospital knowledge base for RAG retrieval

Contains synthetic (non-real) data:
- Doctor profiles and specialties
- Hospital policies
- Medical knowledge base
- Example case descriptions

All data is synthetic and safe for cloud storage.

### 10.3 RAG Retriever (`rag/retriever.py`)

The RAG (Retrieval-Augmented Generation) retriever queries both stores to build rich context for cloud LLM agents:

```python
retrieve_context_for_intent(patient_uuid, intent, semantic_context, medical_info):
    1. Patient history     <- metadata_store.retrieve_patient_history(uuid)
    2. Relevant doctors    <- synthetic_store.search_doctors(specialty)
    3. Medical knowledge   <- synthetic_store.search_medical_knowledge(medical_info)
    4. Similar cases       <- synthetic_store.search_similar_cases(medical_info)

format_context_for_llm(context):
    Formats all retrieved data into structured text sections:
    - "## Patient History (UUID-based)"
    - "## Available Doctors"
    - "## Medical Knowledge"
    - "## Similar Cases"
```

### 10.4 Embeddings

Generated by `rag/embeddings.py` using Sentence Transformers:
- Model: `all-MiniLM-L6-v2` (384 dimensions)
- Used for both storage and retrieval queries
- Cosine similarity metric in Pinecone

---

## 11. Session Management & State Machine

Sessions are managed in-memory by `SessionManager` with a 30-minute timeout.

### Session State Machine

```
                                         +-----------------+
                                         |   NEW SESSION   |
                                         | (no patient)    |
                                         +--------+--------+
                                                  |
                                         User sends message
                                                  |
                                                  v
                                    +-------------+-------------+
                                    | GATEKEEPER EXTRACTS PII   |
                                    +-------------+-------------+
                                                  |
                              +-------------------+-------------------+
                              |                   |                   |
                         0 matches           1 match            2+ matches
                              |                   |                   |
                              v                   v                   v
                    +---------+------+  +---------+------+  +---------+---------+
                    | NEEDS_CONFIRM  |  |    RESOLVED    |  | NEEDS_DISAMBIG    |
                    | (create new?)  |  | (auto-set      |  | (show candidates) |
                    +--------+-------+  |  active patient|  +--------+----------+
                             |          +--------+-------+           |
                       user confirms             |              user selects UUID
                             |                   |                   |
                             v                   v                   v
                    +--------+-------------------+-------------------+---+
                    |              PATIENT ACTIVE IN SESSION              |
                    +--------+-------------------------------------------+
                             |
                    intent = appointment or followup?
                             |
                        +----+----+
                        |  YES    |  NO (general/summary)
                        v         v
              +----+----+--+   Execute immediately
              | COLLECTING |   and return result
              | INFO (HITL)|
              +-----+------+
                    |
              questions answered
                    |
                    v
              +-----+--------+
              | AWAITING     |
              | CONFIRMATION |
              +-----+--------+
                    |
              +-----+-----+
              |           |
           "yes"        "no"
              |           |
              v           v
         +----+---+  +---+------+
         | EXECUTE|  | CANCELLED|
         | ACTION |  +----------+
         +--------+
```

### Context Switch Detection

The `MemoryManager.detect_context_switch()` method detects when a user switches patients:

1. **Explicit keywords:** "switch to", "different patient", "new patient", etc.
2. **Name heuristic:** If a different name appears via the pattern `"my name is X"` / `"patient X"` / `"for X"`
3. **Action without mention:** If the active patient name is NOT mentioned but action verbs like "appointment"/"schedule" appear

When detected, the active patient is cleared and the pipeline re-resolves identity.

---

## 12. Human-in-the-Loop (HITL) Workflow

For `appointment` and `followup` intents, the system collects additional medical information before finalising:

```
Turn 1: User requests appointment
        -> Pipeline runs Steps 1-5 (Gatekeeper -> Context -> Execution)
        -> HITLManager generates 2-3 questions
        -> First question returned to user
        -> Pipeline PAUSES (state saved in session.pending_action)

Turn 2: User answers Question 1
        -> Response recorded in pending_action.user_responses
        -> Question 2 returned

Turn 3: User answers Question 2
        -> Response recorded
        -> Question 3 returned (if applicable)

Turn 4: User answers Question 3 (or Question 2 was last)
        -> All questions answered
        -> HITLManager creates confirmation summary
        -> Summary displayed with "Type 'yes' to proceed"

Turn 5: User types "yes" or "no"
        -> If yes: _finalize_appointment() or _finalize_followup()
           stores medical record, returns success
        -> If no: action cancelled, pending_action cleared
```

**Question examples by category:**

| Category | Questions |
|----------|-----------|
| Respiratory | "How long have you been experiencing these symptoms?", "Do you have difficulty breathing?", "Contact with sick person?" |
| Cardiac | "How long?", "Chest pain or discomfort?", "History of heart conditions?" |
| Neurological | "How long?", "Vision changes or dizziness?", "Recent head injuries?" |
| General | "How long?", "Discomfort rating 1-10?", "Taken any medication?" |

---

## 13. MCP Bridge: Model Context Protocol

**File:** `backend/mcp/bridge.py`
**Singleton:** `mcp_bridge`

The MCP Bridge is an **auditing and enforcement layer** that sits between local agents and cloud APIs. Every payload destined for the cloud passes through it.

### Forbidden Field Names (50+)

```
name, patient_name, full_name, first_name, last_name,
age, dob, date_of_birth,
ssn, social_security,
phone, telephone, mobile,
email, email_address,
address, street, zip_code, postal_code,
gender, sex,
medical_record_number, mrn,
insurance_id, national_id
```

### PII Value Patterns (Regex)

| Pattern | Description |
|---------|-------------|
| `\b\d{3}-\d{2}-\d{4}\b` | SSN (123-45-6789) |
| `[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z]{2,}` | Email address |
| `\b\d{10}\b` | 10-digit phone number |
| `\b\d{3}[\s-]\d{3}[\s-]\d{4}\b` | Phone with dashes/spaces |

### Safe Keys (Skip List)

```
patient_uuid, uuid, session_id, record_id,
intent, action_type, record_type,
privacy_safe, cloud_exposed
```

### Scanning Process

```python
_scan_for_pii(data, path=""):
    if dict:
        for key, value in data.items():
            if key in SAFE_KEYS: skip
            if key in FORBIDDEN_FIELDS: add violation
            recurse into value
    if list/tuple:
        recurse into each element
    if string:
        test against all PII_PATTERNS (regex)
```

### Data Flow Points

The bridge is invoked at every cloud boundary crossing:

1. **Before Context Agent:** `mcp_bridge.route_to_cloud("context_agent", uuid, payload)`
2. **After Context Agent:** `mcp_bridge.route_from_cloud("context_agent", uuid, response)`
3. **Before Execution Agent:** `mcp_bridge.route_to_cloud("execution_agent", uuid, payload)`
4. **After Execution Agent:** `mcp_bridge.route_from_cloud("execution_agent", uuid, response)`
5. **Before Worker Agent (API routes):** `mcp_bridge.route_to_cloud("worker_agent", uuid, payload)`
6. **After Worker Agent (API routes):** `mcp_bridge.route_from_cloud("worker_agent", uuid, response)`

### Audit Log

Each bridge call records:
- `timestamp` (ISO 8601 UTC)
- `direction` ("outgoing" or "incoming")
- `agent_name` (which cloud agent)
- `patient_uuid_prefix` (first 8 chars)
- `safe` (boolean)
- `violations` (list of descriptions)
- `payload_hash` (SHA-256 fingerprint, first 16 hex chars)

### Compliance Report

`GET /api/chat/privacy-report` returns the MCP bridge compliance report:

```json
{
  "total_calls": 42,
  "total_violations": 0,
  "unsafe_calls": 0,
  "compliance_rate": 100.0,
  "privacy_enforced": true,
  "bridge_active": true,
  "agent_breakdown": {
    "context_agent": {"total": 14, "safe": 14, "unsafe": 0},
    "execution_agent": {"total": 14, "safe": 14, "unsafe": 0},
    "worker_agent": {"total": 14, "safe": 14, "unsafe": 0}
  }
}
```

---

## 14. Frontend-Backend Communication

### API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/` | Serve chat dashboard (index.html) |
| `GET` | `/appointment` | Serve appointment form |
| `GET` | `/followup` | Serve follow-up form |
| `GET` | `/summary` | Serve summary form |
| `GET` | `/health` | System health check |
| `POST` | `/api/chat/message` | Process chat message |
| `GET` | `/api/chat/privacy-report` | Privacy compliance report |
| `POST` | `/api/appointments/schedule` | Schedule appointment |
| `POST` | `/api/followups/schedule` | Schedule follow-up |
| `POST` | `/api/summaries/generate` | Generate medical summary |

### Chat Message Request/Response

**Request:**
```json
{
  "message": "I'm John Doe, 35 years old male, having severe headaches",
  "session_id": "optional-session-uuid"
}
```

**Response:**
```json
{
  "success": true,
  "message": "I'll help you with that. First, I need to ask a few questions...",
  "intent": "appointment_initiated",
  "patient_uuid": "a3b7c9d1-...",
  "patient_name": "John Doe",
  "result": {
    "privacy_details": {
      "pii_detected": true,
      "original_contains": {
        "name": "John Doe",
        "age": "35",
        "gender": "Male"
      },
      "pseudonymized_to": "a3b7c9d1-...",
      "transformations": [
        {
          "field": "Patient Name",
          "original": "John Doe",
          "transformed": "Patient_a3b7c9d1",
          "method": "UUID Pseudonymization"
        },
        {
          "field": "Age",
          "original": "35",
          "transformed": "late 20s to early 30s",
          "method": "Age Group Masking"
        }
      ],
      "pii_removed": 2,
      "cloud_safe": true
    },
    "session_id": "abc123..."
  },
  "privacy_safe": true,
  "workflow_steps": [
    "Gatekeeper: PII detection and pseudonymization",
    "Identity Resolution: Patient disambiguation",
    "Metadata Store: UUID-linked context storage",
    "MCP Bridge: Privacy validation (outgoing)",
    "Context Agent: RAG-based context refinement",
    "MCP Bridge: Privacy validation (incoming)",
    "Execution Agent: Task execution",
    "MCP Bridge: Privacy validation (response)",
    "Gatekeeper: Re-identification for output"
  ]
}
```

### Frontend Dashboard Panels

The chat dashboard (`index.html`) has three panels:

1. **Left Navigation** -- Links to Chat, Appointments, Follow-ups, Summaries
2. **Center Chat Panel** -- Message input, conversation history, typing indicators
3. **Right Process Monitor** -- Real-time pipeline step visualisation using `workflow_steps`, privacy details display showing PII transformations

---

## 15. Configuration & Environment

### `.env` File (project root)

| Variable | Description | Example |
|----------|-------------|---------|
| `GROQ_API_KEY` | Groq cloud LLM API key | `gsk_...` |
| `PINECONE_API_KEY` | Pinecone vector store key | `pc-...` |
| `PINECONE_ENVIRONMENT` | Pinecone AWS region | `us-east-1` |
| `PINECONE_INDEX_METADATA` | Metadata index name | `medshield-metadata` |
| `PINECONE_INDEX_SYNTHETIC` | Synthetic index name | `medshield-synthetic` |
| `OLLAMA_HOST` | Ollama LLM server URL | `http://localhost:11434` |
| `OLLAMA_MODEL` | Local LLM model name | `gemma3:1b` |
| `OPENAI_API_KEY` | Optional, for embeddings | `sk-...` |
| `SQLITE_DB_PATH` | SQLite database path | `./backend/database/identity_vault.db` |
| `BACKEND_HOST` | Server bind address | `127.0.0.1` |
| `BACKEND_PORT` | Server port | `8000` |
| `FRONTEND_URL` | Frontend URL | `http://localhost:8000` |
| `LOG_LEVEL` | Logging verbosity | `INFO` |
| `TESTING_MODE` | Enable test mode | `False` |
| `SECRET_KEY` | Application secret | `change-this-in-production` |

### Config Loading

Settings are managed by `pydantic_settings.BaseSettings` in `backend/utils/config.py`. The `.env` file is located at `Path(__file__).parent.parent.parent / ".env"` (project root).

---

## 16. Testing

### Running Tests

```bash
cd backend
python -m pytest tests/ -v
```

### Test Mode Behaviour

When `TESTING_MODE=True`:
- `GatekeeperAgent.pseudonymize_input()` uses regex extraction instead of Ollama calls
- `CoordinatorAgent` uses rule-based planning instead of Groq API
- Vector stores use `MockMetadataStore` and `MockSyntheticStore`
- `SemanticStore` is replaced with `MockSemanticStore`

### Mock Stores

| Mock | Replaces | Behaviour |
|------|----------|-----------|
| `MockMetadataStore` | `MetadataStore` | Returns empty lists, accepts store calls |
| `MockSyntheticStore` | `SyntheticStore` | Returns empty lists for searches |
| `MockSemanticStore` | `SemanticStore` | Returns empty semantic anchors |

---

## Summary of Data Flow Guarantees

| Data Type | Stored Locally | Sent to Cloud | Stored in Pinecone |
|-----------|:-:|:-:|:-:|
| Patient Name | Yes (SQLite) | Never | Never |
| Exact Age | Yes (SQLite) | Never | Never |
| Gender | Yes (SQLite) | Never | Never |
| Patient UUID | Yes (SQLite) | Yes | Yes |
| Age Group | No | Yes | No |
| Symptom Category | No | Yes | Yes |
| Urgency Level | No | Yes | Yes |
| Medical Records | Yes (SQLite) | Never | Never |
| Interaction History | No | N/A | Yes (UUID-only) |
| Audit Logs | Yes (SQLite) | Never | Never |
| MCP Audit Log | Yes (in-memory) | Never | Never |
