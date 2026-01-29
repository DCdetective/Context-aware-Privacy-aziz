import pytest
from fastapi.testclient import TestClient
from main import app
import time


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestPerformance:
    """Performance tests for the system."""
    
    def test_appointment_response_time(self, client):
        """Test that appointment scheduling completes in reasonable time."""
        request_data = {
            "patient_name": "Performance Test Patient",
            "age": 35,
            "gender": "Male",
            "symptoms": "Performance test"
        }
        
        start_time = time.time()
        response = client.post("/api/appointments/schedule", json=request_data)
        end_time = time.time()
        
        response_time = end_time - start_time
        
        print(f"\nAppointment Response Time: {response_time:.2f} seconds")
        
        assert response.status_code == 200
        # Should complete within 30 seconds (allowing for LLM calls)
        assert response_time < 30, f"Response too slow: {response_time:.2f}s"
    
    def test_concurrent_requests(self, client):
        """Test handling of concurrent requests."""
        import concurrent.futures
        
        def make_request(patient_num):
            request_data = {
                "patient_name": f"Concurrent Patient {patient_num}",
                "age": 30 + patient_num,
                "gender": "Male" if patient_num % 2 == 0 else "Female",
                "symptoms": f"Concurrent test {patient_num}"
            }
            response = client.post("/api/appointments/schedule", json=request_data)
            return response.status_code == 200
        
        # Test with 5 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request, i) for i in range(5)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        # All requests should succeed
        assert all(results), "Some concurrent requests failed"
        print(f"\n✅ Handled {len(results)} concurrent requests successfully")
