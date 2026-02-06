# MedShield Test Suite Documentation

## Test Categories

### Unit Tests
- `test_agents.py` – Agent initialization and basic operations
- `test_gatekeeper.py` – Gatekeeper PII detection and anonymization
- `test_gatekeeper_privacy.py` – Gatekeeper privacy guarantee verification
- `test_identity_vault.py` – Identity vault CRUD operations
- `test_session_manager.py` – Session state management
- `test_context_agent.py` – Context agent storage and retrieval
- `test_worker.py` – Worker agent task execution
- `test_patient_registry.py` – Patient registry operations
- `test_synthetic_data.py` – Synthetic data loading
- `test_vector_stores.py` – Vector store operations
- `test_semantic_store.py` – Semantic store operations

### Integration Tests
- `test_integration.py` – Component integration (Gatekeeper ↔ Vault, Coordinator ↔ Session Manager, etc.)
- `test_coordinator.py` – Coordinator agent orchestration
- `test_appointment_workflow.py` – Complete appointment workflow
- `test_followup_workflow.py` – Follow-up workflow
- `test_summary_generation.py` – Summary generation workflow
- `test_hitl_workflow.py` – Human-in-the-loop workflow
- `test_identity_resolution.py` – Patient identity resolution
- `test_memory_system.py` – Memory manager operations

### E2E Tests
- `test_e2e_workflow.py` – Full user journeys (appointment, follow-up, summary)
- `test_chat_interface.py` – Unified chat endpoint testing

### API Tests
- `test_api_routes.py` – Direct API endpoint testing

### Performance Tests
- `test_performance.py` – Response time benchmarks and scalability

### Privacy Tests
- `test_privacy_compliance.py` – Privacy compliance verification
- `test_gatekeeper_privacy.py` – PII handling verification

## Running Tests

```bash
cd backend

# All tests
python -m pytest tests/ -v

# Specific test file
python -m pytest tests/test_e2e_workflow.py -v

# Specific test class
python -m pytest tests/test_e2e_workflow.py::TestE2EWorkflow -v

# Specific test
python -m pytest tests/test_e2e_workflow.py::TestE2EWorkflow::test_complete_appointment_workflow -v

# With coverage
python -m pytest tests/ --cov=agents --cov=routes --cov=database --cov-report=html

# Performance tests
python -m pytest tests/test_performance.py -v

# Privacy tests only
python -m pytest tests/test_privacy_compliance.py tests/test_gatekeeper_privacy.py -v

# Run with output visible
python -m pytest tests/ -v -s

# Run and stop at first failure
python -m pytest tests/ -v -x
```

## Writing Tests

Follow the Arrange-Act-Assert pattern:

```python
def test_feature_name():
    # Arrange: Setup
    patient = create_test_patient()

    # Act: Execute
    result = perform_action(patient)

    # Assert: Verify
    assert result.success is True
```

### Fixtures (conftest.py)

| Fixture | Description |
|---------|-------------|
| `client` | FastAPI TestClient instance |
| `test_vault` | Temporary identity vault (cleaned up after test) |
| `mock_metadata_store` | Mock metadata vector store |
| `mock_synthetic_store` | Mock synthetic data store |
| `sample_patient_data` | Sample patient data dict |
| `sample_messages` | Sample chat messages for different intents |

### Pre-creating Patients for Tests

When testing workflows that require existing patients, pre-create them to avoid the "confirmation_required" flow:

```python
def test_with_existing_patient(self, client):
    from database.identity_vault import identity_vault
    identity_vault.pseudonymize_patient(
        patient_name="Test Patient",
        age=30,
        gender="Male",
        component="test"
    )
    # Now the patient exists and won't trigger confirmation
    response = client.post("/api/chat/message",
        json={"message": "I'm Test Patient, 30, male. Book appointment."})
```

## Test Coverage Goals

- Unit tests: 80%+ coverage
- Integration tests: All major component interactions
- E2E tests: All user journeys
- Privacy tests: 100% of privacy-critical paths
- Performance tests: All response time benchmarks

## Privacy Testing

Critical privacy tests ensure:

1. No PII in cloud storage (Pinecone vectors)
2. UUID-only in cloud agent communication
3. Audit trails complete and accurate
4. Re-identification only at final output
5. Data separation maintained (local PII vs cloud semantics)
6. No PII leakage in API logs
