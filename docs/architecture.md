# MedShield System Architecture

## Overview

MedShield is a privacy-preserving multi-agent medical assistant designed to ensure that Personally Identifiable Information (PII) never leaves the trusted local environment while still enabling powerful cloud-based medical reasoning.

## Core Privacy Principle

**NO PII EVER LEAVES THE LOCAL ENVIRONMENT**

All cloud-based reasoning operates exclusively on pseudonymized UUID identifiers and non-sensitive semantic anchors.

## System Components

### 1. Local Gatekeeper Agent (Ollama - Llama 3.1)

**Location:** Local Machine  
**Purpose:** First line of privacy defense  

**Responsibilities:**
- Detect and extract PII from user input
- Generate/retrieve UUID mappings via Identity Vault
- Extract semantic (non-PII) medical context
- Re-identify patients for final output display
- NEVER allow PII to reach cloud agents

**Key Operations:**
```
User Input → PII Detection → Pseudonymization → UUID + Semantic Context
Cloud Response + UUID → Re-identification → User Output with Real Identity
```

### 2. Local Identity Vault (SQLite)

**Location:** Local Machine  
**Purpose:** Secure PII storage and reversible mapping  

**Responsibilities:**
- Store patient identities (name, age, gender)
- Maintain bidirectional UUID ↔ Identity mapping
- Store medical records locally
- Maintain complete audit trail
- NEVER expose database to network

**Database Schema:**
- `patient_identities`: UUID ↔ PII mapping
- `medical_records`: Patient medical data
- `audit_logs`: Complete operation trail

### 3. Semantic Anchor Store (Pinecone Vector DB)

**Location:** Cloud (Privacy-Safe)  
**Purpose:** Store non-PII medical context  

**Responsibilities:**
- Store semantic medical preferences and constraints
- Enable context-aware medical reasoning
- Support vector similarity search
- Validate NO PII in stored data

**Allowed Data:**
- Medical preference categories
- Semantic constraints (accessibility needs)
- Treatment response patterns (anonymized)
- Follow-up scheduling requirements

**Forbidden Data:**
- Patient names, ages, genders
- Specific diagnoses with identifying details
- Any information that could identify a patient

### 4. Cloud Coordinator Agent (Groq API)

**Location:** Cloud  
**Purpose:** Task planning and orchestration  

**Responsibilities:**
- Receive pseudonymized requests (UUID only)
- Plan medical task execution
- Create execution plans based on semantic context
- Delegate tasks to Worker Agent
- NEVER access Identity Vault

**Input:** `patient_uuid` + `semantic_context`  
**Output:** `execution_plan`

### 5. Cloud Worker Agent (Groq API)

**Location:** Cloud  
**Purpose:** Medical task execution  

**Responsibilities:**
- Execute appointments, follow-ups, summaries
- Validate patient existence by UUID only
- Use semantic context for medical logic
- Store results linked to UUID
- NEVER access real patient identities

**Supported Actions:**
1. Appointment Scheduling
2. Follow-Up Planning
3. Medical Summary Generation

### 6. MCP Server

**Location:** Local Machine  
**Purpose:** Secure execution bridge  

**Responsibilities:**
- Bridge between local and cloud components
- Enforce privacy boundaries
- Validate data flows
- Ensure separation of concerns

## Data Flow Architecture

### Complete Workflow Example: Appointment Scheduling

```
┌─────────────────────────────────────────────────────────────────┐
│                         FRONTEND (Browser)                       │
│  User enters: Name, Age, Gender, Symptoms                       │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FASTAPI BACKEND                             │
│  POST /api/appointments/schedule                                │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              LOCAL GATEKEEPER AGENT (Ollama)                     │
│  Step 1: Extract PII from input                                 │
│          - Name: "John Doe"                                     │
│          - Age: 45, Gender: Male                                │
│          - Symptoms: "Headache"                                 │
│                                                                  │
│  Step 2: Pseudonymize via Identity Vault                       │
│          - Generate UUID: "a1b2c3d4-..."                        │
│          - Store: UUID ↔ "John Doe" mapping                    │
│                                                                  │
│  Step 3: Extract Semantic Context (NO PII)                     │
│          - symptom_category: "neurological"                     │
│          - urgency_level: "routine"                             │
│          - requires_specialist: false                           │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
           ┌───────────────────────────────┐
           │   CLOUD BOUNDARY (Privacy)    │
           │   Only UUID + Semantic Data   │
           └───────────────┬───────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│          CLOUD COORDINATOR AGENT (Groq API)                      │
│  Receives:                                                       │
│    - patient_uuid: "a1b2c3d4-..."                              │
│    - semantic_context: {category: "neurological", ...}         │
│                                                                  │
│  Creates Execution Plan:                                        │
│    - steps: [validate, schedule, confirm]                      │
│    - priority: "routine"                                        │
│    - estimated_time: 30 minutes                                 │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│            CLOUD WORKER AGENT (Groq API)                         │
│  Step 1: Validate UUID exists (no PII access)                  │
│  Step 2: Calculate appointment time based on urgency           │
│  Step 3: Store record in Identity Vault (by UUID)              │
│  Step 4: Return result with UUID                                │
│                                                                  │
│  Output:                                                         │
│    - patient_uuid: "a1b2c3d4-..."                              │
│    - appointment_time: "2024-01-20T10:00:00"                   │
│    - consultation_duration: 30                                  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
           ┌───────────────────────────────┐
           │   CLOUD BOUNDARY (Privacy)    │
           │   Result contains only UUID   │
           └───────────────┬───────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              LOCAL GATEKEEPER AGENT (Ollama)                     │
│  Step 1: Receive cloud response with UUID                      │
│  Step 2: Re-identify via Identity Vault                        │
│          - UUID "a1b2c3d4-..." → "John Doe"                   │
│  Step 3: Merge identity with response                          │
│                                                                  │
│  Final Output:                                                  │
│    - patient_name: "John Doe"                                  │
│    - appointment_time: "2024-01-20T10:00:00"                   │
│    - All other details...                                       │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FASTAPI BACKEND                             │
│  Returns JSON response to frontend                              │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                         FRONTEND (Browser)                       │
│  Displays: "Appointment scheduled for John Doe at 10:00 AM"    │
└─────────────────────────────────────────────────────────────────┘
```

## Privacy Guarantees

### 1. PII Never Leaves Local Environment

**Enforcement Mechanisms:**
- Gatekeeper acts as privacy gateway
- Identity Vault only accessible locally
- Cloud agents receive UUID + semantic data only
- Audit trail verifies no cloud exposure

### 2. Cloud Agents are Identity-Blind

**Implementation:**
- Coordinator and Worker agents never see patient names
- UUID validation checks existence without revealing identity
- Semantic context contains no identifying information
- Re-identification happens only at final output stage

### 3. Semantic Store is Privacy-Safe

**Validation:**
- Automatic PII detection before storage
- Forbidden fields rejected (name, age, gender)
- Only non-sensitive medical context stored
- Cloud storage is safe as data contains no PII

### 4. Complete Audit Trail

**Tracking:**
- Every identity vault operation logged
- PII access tracked by component
- Cloud exposure flag (must always be False)
- Complete workflow traceability

## Security Considerations

### Local Components Security

1. **SQLite Database:** File-based, local-only access
2. **Ollama Instance:** Runs locally, no external calls
3. **File Permissions:** Restrict database access
4. **Network Isolation:** Identity Vault not exposed

### Cloud Components Security

1. **API Key Management:** Groq and Pinecone keys in .env
2. **HTTPS Communication:** All API calls encrypted
3. **Data Minimization:** Only necessary data sent to cloud
4. **No PII Storage:** Cloud stores only UUIDs and semantic data

### Audit and Compliance

1. **Complete Logging:** All operations tracked
2. **Privacy Verification:** Automated compliance tests
3. **Traceability:** UUID-based operation tracking
4. **Academic Transparency:** Logs suitable for demonstration

## Technology Stack

### Backend
- **Framework:** FastAPI (Python 3.12.2)
- **Local LLM:** Ollama (Llama 3.1)
- **Cloud LLM:** Groq API (Llama 3.1 70B)
- **Vector DB:** Pinecone (Free Tier)
- **Local DB:** SQLite
- **Environment:** Python Virtual Environment

### Frontend
- **HTML5:** Semantic structure
- **CSS3:** Modern styling
- **JavaScript:** Vanilla JS (no frameworks)
- **Design:** Medical theme, professional UI

### Deployment
- **Local Server:** Uvicorn ASGI server
- **Port:** 8000 (configurable)
- **Environment:** .env configuration

## Scalability Considerations

### Current Implementation
- Single-user local deployment
- SQLite for simplicity
- Mock semantic store for testing

### Production Scaling Path
1. Replace SQLite with PostgreSQL
2. Add authentication and authorization
3. Implement proper MCP server
4. Add caching layer
5. Deploy with Docker/Kubernetes
6. Add monitoring and alerting

## Academic Evaluation Points

### Key Demonstration Areas

1. **Privacy Architecture:** Show PII never reaches cloud
2. **Multi-Agent Coordination:** Demonstrate agent interactions
3. **Audit Trail:** Display complete operation tracking
4. **UI/UX:** Professional medical interface
5. **Testing:** Comprehensive test coverage
6. **Documentation:** Clear system explanation

### Viva Preparation

**Expected Questions:**
1. How do you ensure PII never leaves local environment?
2. What happens if cloud agents try to access PII?
3. How do you maintain medical context without identity?
4. What are the limitations of this approach?
5. How would you scale this system?

**Answers:**
1. Gatekeeper pseudonymization + Audit trail + Automated tests
2. Impossible - cloud agents only receive UUIDs
3. Semantic Anchor Store with UUID-based indexing
4. Requires local compute, latency from cloud calls
5. Add auth, scale DB, containerize, add caching

## Conclusion

MedShield demonstrates a novel approach to privacy-preserving AI in healthcare by combining local PII protection with cloud-based reasoning capabilities. The multi-agent architecture ensures complete separation of identity from medical logic while maintaining continuity of care.
