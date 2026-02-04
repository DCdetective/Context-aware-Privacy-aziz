# MedShield v2 Test Suite

## Running Tests

### Run all tests:
```bash
python run_tests.py
```

### Run specific test file:
```bash
pytest tests/test_e2e_workflow.py -v
```

### Run specific test:
```bash
pytest tests/test_e2e_workflow.py::TestE2EWorkflow::test_complete_appointment_workflow -v
```

### Run with coverage:
```bash
pytest tests/ --cov=. --cov-report=html
```

## Test Structure

- `test_gatekeeper.py` - Gatekeeper agent tests
- `test_agents.py` - Cloud agent tests
- `test_identity_vault.py` - Identity vault tests
- `test_vector_stores.py` - Vector store tests
- `test_synthetic_data.py` - Synthetic data tests
- `test_e2e_workflow.py` - End-to-end workflow tests
- `test_privacy_compliance.py` - Privacy compliance tests
- `test_performance.py` - Performance tests

## Test Coverage Goals

- Unit tests: 80%+ coverage
- Integration tests: All major workflows
- E2E tests: All user journeys
- Privacy tests: 100% of privacy-critical paths

## Privacy Testing

Critical privacy tests ensure:
1. No PII in cloud storage
2. UUID-only in cloud agents
3. Audit trails complete
4. Re-identification only at output
5. Data separation maintained
