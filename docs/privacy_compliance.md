# MedShield Privacy Compliance Documentation

## Overview

MedShield is a **privacy-preserving medical assistant** that ensures no Personally Identifiable Information (PII) is ever exposed to cloud services. This document details the privacy architecture, guarantees, and compliance verification.

---

## Privacy Architecture

### Data Flow

```
User Input (contains PII)
    ↓
┌─────────────────────────────────┐
│  GATEKEEPER (Local)             │
│  - Detect PII (names, ages,     │
│    phones, addresses, SSNs)     │
│  - Anonymize: Name → UUID       │
│  - Anonymize: Age → Age Bucket  │
│  - Anonymize: Phone → PHONE_XXX │
│  - Store mapping locally         │
└─────────────────────────────────┘
    ↓ (Anonymized data only)
┌─────────────────────────────────┐
│  CLOUD SERVICES                 │
│  - Groq LLM (UUID only)        │
│  - Pinecone (semantic anchors)  │
│  - NO PII ever reaches cloud    │
└─────────────────────────────────┘
    ↓ (UUID-based response)
┌─────────────────────────────────┐
│  GATEKEEPER (Local)             │
│  - Re-identify: UUID → Name     │
│  - Restore real patient info    │
│  - Display to user locally      │
└─────────────────────────────────┘
    ↓
User sees response with real names
```

### PII Classification

| PII Type | Detection Method | Anonymization Method |
|----------|-----------------|---------------------|
| Patient Name | Regex + Local LLM | UUID pseudonymization |
| Age | Regex pattern | Age bucket (e.g., "early 20s") |
| Phone Number | Regex pattern | "PHONE_XXX" |
| Address | Regex pattern | "residential area" |
| SSN | Regex pattern | "SSN_REDACTED" |

### Age Buckets

| Age Range | Bucket Label |
|-----------|-------------|
| 0-12 | child |
| 13-17 | teenager |
| 18-25 | early 20s |
| 26-35 | late 20s to early 30s |
| 36-50 | middle-aged |
| 51-65 | senior |
| 66+ | elderly |

---

## Privacy Guarantees

### 1. No PII in Cloud Storage
- Pinecone vectors contain only UUIDs and semantic categories
- No patient names, ages, or contact info in cloud
- Verified by `test_privacy_compliance.py::test_no_pii_in_vector_stores`

### 2. No PII in Cloud LLM Requests
- Groq API receives only anonymized text with UUIDs
- Gatekeeper intercepts all outgoing requests
- Verified by `test_privacy_compliance.py::test_no_pii_in_api_logs`

### 3. Complete Audit Trail
- Every data access logged with timestamp, component, and operation
- Cloud exposure flag tracked (should always be False)
- Verified by `test_privacy_compliance.py::test_identity_vault_audit_trail`

### 4. Re-identification Only at Output
- Patient names restored only at the final display step
- Internal processing uses UUIDs exclusively
- Verified by `test_privacy_compliance.py::test_reidentification_only_at_output`

### 5. Data Separation
- PII stored in local SQLite database (never leaves server)
- Non-PII semantic data stored in cloud vector stores
- Verified by `test_privacy_compliance.py::TestDataSeparation`

---

## Compliance Verification

### Automated Tests

```bash
cd backend

# Run all privacy tests
python -m pytest tests/test_privacy_compliance.py -v

# Run gatekeeper privacy tests
python -m pytest tests/test_gatekeeper_privacy.py -v

# Run full privacy report
python -m pytest tests/test_privacy_compliance.py tests/test_gatekeeper_privacy.py -v
```

### Privacy Report API

```bash
curl http://localhost:8000/api/chat/privacy-report
```

Returns:
```json
{
    "report": {
        "total_patients": 15,
        "total_operations": 142,
        "cloud_exposed_count": 0,
        "privacy_compliant": true
    }
}
```

### Manual Verification Checklist

- [ ] No PII in Pinecone metadata
- [ ] No PII in Groq API request logs
- [ ] All PII transformations logged in audit trail
- [ ] Re-identification happens only locally
- [ ] Audit trail shows cloud_exposed = False for all operations
- [ ] Age values converted to buckets before cloud transmission
- [ ] Phone numbers masked before cloud transmission
- [ ] Addresses generalized before cloud transmission

---

## Incident Response

If a privacy violation is detected:

1. **Immediately** check audit logs for `cloud_exposed = True`
2. **Identify** the component that leaked PII
3. **Review** Gatekeeper anonymization rules
4. **Update** PII detection patterns in `utils/pii_patterns.py`
5. **Add** regression test for the specific violation
6. **Verify** fix with full privacy test suite
