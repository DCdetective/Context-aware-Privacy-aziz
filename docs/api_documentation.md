# MedShield API Documentation

## Overview

MedShield provides a RESTful API for a privacy-preserving medical chatbot system. All endpoints ensure that **no PII (Personally Identifiable Information) is ever sent to cloud services**.

**Base URL:** `http://localhost:8000`

---

## Chat API

### POST /api/chat/message

Main conversational endpoint. Handles ALL conversation types (appointments, follow-ups, summaries, general queries) through a single unified interface.

**Request:**
```json
{
    "message": "Book appointment for Aziz",
    "session_id": "optional-uuid"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message` | string | Yes | User's input message (may contain PII) |
| `session_id` | string | No | Session UUID for conversation continuity |

**Response:**
```json
{
    "success": true,
    "message": "I'll help you book an appointment...",
    "intent": "appointment",
    "patient_uuid": "abc12345-...",
    "patient_name": "Aziz",
    "result": {
        "appointment_time": "2026-02-13T14:00:00",
        "consultation_duration": 30,
        "urgency_level": "routine",
        "privacy_details": {
            "transformations": [...],
            "pii_removed": 2,
            "cloud_safe": true
        },
        "session_id": "session-uuid"
    },
    "privacy_safe": true,
    "workflow_steps": ["Gatekeeper", "Identity Resolution", "Context Agent", "Execution Agent"]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `success` | boolean | Whether the request was processed successfully |
| `message` | string | Human-readable response message |
| `intent` | string | Detected intent: `appointment`, `followup`, `summary`, `general`, `confirmation_required`, `disambiguation_required` |
| `patient_uuid` | string? | Patient's anonymized UUID |
| `patient_name` | string? | Patient's real name (re-identified locally) |
| `result` | object | Detailed result data |
| `privacy_safe` | boolean | Whether privacy was maintained |
| `workflow_steps` | array | Steps executed in the pipeline |

---

### GET /api/chat/privacy-report

Get privacy compliance report for the system.

**Response:**
```json
{
    "success": true,
    "report": {
        "total_patients": 15,
        "total_operations": 142,
        "cloud_exposed_count": 0,
        "privacy_compliant": true,
        "timestamp": "2026-02-06T00:00:00Z"
    },
    "message": "Privacy compliance verified"
}
```

---

## Appointments API

### POST /api/appointments/schedule

Schedule a new appointment with the full privacy-preserving workflow.

**Request:**
```json
{
    "patient_name": "John Doe",
    "age": 45,
    "gender": "Male",
    "symptoms": "Persistent chest pain and shortness of breath"
}
```

**Response:**
```json
{
    "success": true,
    "message": "Appointment scheduled successfully for John Doe",
    "patient_name": "John Doe",
    "patient_uuid": "abc12345-...",
    "appointment_time": "2026-02-13T14:00:00",
    "consultation_duration": 30,
    "urgency_level": "routine",
    "record_id": "rec-uuid"
}
```

---

## Follow-ups API

### POST /api/followups/schedule

Schedule a follow-up appointment for an existing patient.

**Request:**
```json
{
    "patient_name": "John Doe"
}
```

**Response:**
```json
{
    "success": true,
    "message": "Follow-up scheduled successfully for John Doe",
    "patient_name": "John Doe",
    "patient_uuid": "abc12345-...",
    "followup_time": "2026-02-20T10:00:00",
    "previous_visits": 3,
    "continuity_maintained": true,
    "record_id": "rec-uuid"
}
```

---

## Summaries API

### POST /api/summaries/generate

Generate a privacy-safe medical summary for a patient.

**Request:**
```json
{
    "patient_name": "John Doe"
}
```

**Response:**
```json
{
    "success": true,
    "message": "Medical summary generated for John Doe",
    "patient_name": "John Doe",
    "patient_uuid": "abc12345-...",
    "summary": {
        "total_visits": 5,
        "record_types": ["appointment", "followup"],
        "summary_text": "Patient has 5 medical records..."
    },
    "record_id": "rec-uuid"
}
```

---

## Health Check

### GET /health

System health check endpoint.

**Response:**
```json
{
    "status": "healthy",
    "service": "MedShield v2",
    "version": "2.0.0",
    "components": {
        "identity_vault": "operational",
        "semantic_store": "operational",
        "gatekeeper_agent": "operational",
        "coordinator_agent": "operational",
        "worker_agent": "operational"
    }
}
```

---

## Frontend Pages

| Route | Method | Description |
|-------|--------|-------------|
| `/` | GET | Main unified chat interface |
| `/appointment` | GET | Appointment booking page (legacy) |
| `/followup` | GET | Follow-up scheduling page (legacy) |
| `/summary` | GET | Medical summary page (legacy) |

---

## Error Responses

All endpoints return standard error responses:

```json
{
    "detail": "Error description"
}
```

| Status Code | Description |
|-------------|-------------|
| 200 | Success |
| 400 | Bad Request (invalid input) |
| 404 | Not Found (patient/resource not found) |
| 422 | Validation Error (missing required fields) |
| 500 | Internal Server Error |

---

## Privacy Guarantees

1. **No PII in cloud requests**: All patient data is anonymized before any cloud API call
2. **UUID-only in cloud**: Cloud services only see patient UUIDs, never names or ages
3. **Local re-identification**: Patient names are restored only at the final output stage
4. **Audit trail**: Every data access is logged for compliance verification
5. **Semantic extraction**: Medical context is extracted without PII
