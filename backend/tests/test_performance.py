import pytest
import time


class TestPerformance:
    """Test system performance."""
    
    def test_chat_response_time(self, client):
        """Test chat response time is acceptable."""
        message = "I'm Speed Test, 30, male. Quick appointment please."
        
        start_time = time.time()
        response = client.post("/api/chat/message", json={"message": message})
        end_time = time.time()
        
        duration = end_time - start_time
        
        assert response.status_code == 200
        assert duration < 30.0  # Should respond within 30 seconds
    
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


class TestScalability:
    """Test system scalability."""
    
    def test_many_patients(self, test_vault):
        """Test handling many patients."""
        # Create 100 patients
        uuids = []
        for i in range(100):
            uuid, _ = test_vault.pseudonymize_patient(
                patient_name=f"Patient {i}",
                age=20 + (i % 60),
                gender="Male" if i % 2 == 0 else "Female"
            )
            uuids.append(uuid)
        
        # Verify all unique
        assert len(set(uuids)) == 100
        
        # Verify can retrieve all
        for uuid in uuids[:10]:  # Test first 10
            identity = test_vault.reidentify_patient(uuid)
            assert identity is not None
