# MedShield Test Suite

## Test Organization

### Unit Tests
- `test_identity_vault.py` - Local identity vault operations
- `test_semantic_store.py` - Semantic anchor store operations
- `test_gatekeeper.py` - Gatekeeper agent functionality
- `test_coordinator.py` - Coordinator agent functionality
- `test_worker.py` - Worker agent functionality

### Integration Tests
- `test_api_routes.py` - API endpoint integration
- `test_e2e_workflow.py` - End-to-end workflow tests

### Compliance Tests
- `test_privacy_compliance.py` - Privacy compliance verification

### Performance Tests
- `test_performance.py` - Response time and concurrency tests

## Running Tests

### Run All Tests
```bash
cd backend
python run_tests.py
```

### Run Specific Test Suite
```bash
pytest tests/test_identity_vault.py -v
```

### Run with Coverage
```bash
pytest tests/ --cov=. --cov-report=html
```

### Run Privacy Compliance Tests Only
```bash
pytest tests/test_privacy_compliance.py -v
```

## Test Requirements

- All tests must pass before deployment
- Privacy compliance tests are CRITICAL
- E2E tests validate complete workflows
- Performance tests ensure acceptable response times

## Privacy Test Verification

The following MUST always be true:
1. NO PII in semantic store
2. NO cloud-exposed operations in audit trail
3. UUID-only communication with cloud agents
4. Complete audit trail for all operations
