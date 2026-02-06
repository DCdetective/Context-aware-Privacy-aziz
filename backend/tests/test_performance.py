"""
Performance Tests (Prompt 11)

Tests system performance and scalability:
- Response time benchmarks
- Concurrent session handling
- Identity vault throughput
- Scalability under load
"""

import pytest
import time
import threading


class TestPerformance:
    """Test system performance."""

    def test_chat_response_time(self, client):
        """Test chat response time is acceptable (< 30s)."""
        message = "I'm Speed Test, 30, male. Quick appointment please."

        start_time = time.time()
        response = client.post("/api/chat/message", json={"message": message})
        end_time = time.time()

        duration = end_time - start_time

        assert response.status_code == 200
        assert duration < 30.0  # Should respond within 30 seconds

    def test_simple_query_response_time(self, client):
        """Test simple query responds quickly (< 10s)."""
        start_time = time.time()
        response = client.post(
            "/api/chat/message",
            json={"message": "What services do you provide?"}
        )
        end_time = time.time()

        duration = end_time - start_time
        assert response.status_code == 200
        assert duration < 10.0

    def test_health_check_response_time(self, client):
        """Test health check is fast (< 1s)."""
        start_time = time.time()
        response = client.get("/health")
        end_time = time.time()

        duration = end_time - start_time
        assert response.status_code == 200
        assert duration < 1.0

    def test_patient_lookup_response_time(self, test_vault):
        """Test patient lookup is fast (< 500ms)."""
        # Create patient
        uuid_val, _ = test_vault.pseudonymize_patient(
            patient_name="Lookup Speed Test",
            age=30,
            gender="Male"
        )

        start_time = time.time()
        identity = test_vault.reidentify_patient(uuid_val)
        end_time = time.time()

        duration = end_time - start_time
        assert identity is not None
        assert duration < 0.5

    def test_multiple_sequential_requests(self, client):
        """Test handling multiple sequential requests."""
        messages = [
            "I'm Test Patient 1, 20, female. I need help.",
            "I'm Test Patient 2, 30, male. I need an appointment.",
            "I'm Test Patient 3, 40, female. Can you generate my summary?"
        ]

        start_time = time.time()

        success_count = 0
        for msg in messages:
            response = client.post("/api/chat/message", json={"message": msg})
            if response.status_code == 200:
                success_count += 1

        end_time = time.time()
        duration = end_time - start_time

        # Should handle 3 requests in reasonable time
        assert duration < 60.0
        # At least 2 out of 3 should succeed
        assert success_count >= 2

    def test_identity_vault_performance(self, test_vault):
        """Test identity vault operations are fast."""
        # Test pseudonymization speed
        start = time.time()

        for i in range(10):
            test_vault.pseudonymize_patient(
                patient_name=f"Patient {i}",
                age=20 + i,
                gender="Male" if i % 2 == 0 else "Female"
            )

        duration = time.time() - start

        # 10 operations should be fast
        assert duration < 5.0

    def test_privacy_report_response_time(self, client):
        """Test privacy report generation is fast (< 2s)."""
        start_time = time.time()
        response = client.get("/api/chat/privacy-report")
        end_time = time.time()

        duration = end_time - start_time
        assert response.status_code == 200
        assert duration < 2.0


class TestConcurrency:
    """Test concurrent session handling."""

    def test_concurrent_identity_vault_operations(self, test_vault):
        """Test concurrent identity vault operations don't conflict."""
        results = []
        errors = []

        def create_patient(i):
            try:
                uuid_val, _ = test_vault.pseudonymize_patient(
                    patient_name=f"Concurrent Patient {i}",
                    age=20 + i,
                    gender="Male" if i % 2 == 0 else "Female"
                )
                results.append(uuid_val)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=create_patient, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0, f"Errors during concurrent operations: {errors}"
        assert len(results) == 10
        # All UUIDs should be unique
        assert len(set(results)) == 10


class TestScalability:
    """Test system scalability."""

    def test_many_patients(self, test_vault):
        """Test handling many patients."""
        # Create 100 patients
        uuids = []
        for i in range(100):
            uuid_val, _ = test_vault.pseudonymize_patient(
                patient_name=f"Patient {i}",
                age=20 + (i % 60),
                gender="Male" if i % 2 == 0 else "Female"
            )
            uuids.append(uuid_val)

        # Verify all unique
        assert len(set(uuids)) == 100

        # Verify can retrieve all
        for uuid_val in uuids[:10]:  # Test first 10
            identity = test_vault.reidentify_patient(uuid_val)
            assert identity is not None

    def test_many_audit_logs(self, test_vault):
        """Test audit log retrieval at scale."""
        # Create patient with many operations
        uuid_val, _ = test_vault.pseudonymize_patient(
            patient_name="Audit Scale Test",
            age=30,
            gender="Male"
        )

        # Perform many operations
        for i in range(20):
            test_vault.reidentify_patient(uuid_val, component=f"test_{i}")

        # Retrieve audit logs
        logs = test_vault.get_audit_logs(patient_uuid=uuid_val)
        assert len(logs) > 0

    def test_large_message_handling(self, client):
        """Test handling of large messages."""
        # Create a reasonably large message
        large_message = "I need an appointment. " * 50
        response = client.post(
            "/api/chat/message",
            json={"message": large_message}
        )
        assert response.status_code in [200, 400]
