from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)


class MockMetadataStore:
    """Mock metadata store for testing."""
    
    def __init__(self):
        self.data = {}
        self.dimension = 384
        self.index_name = "mock-metadata"
    
    def store_patient_metadata(self, patient_uuid: str, semantic_context: Dict[str, Any],
                               intent: str, timestamp: Optional[str] = None) -> str:
        if patient_uuid not in self.data:
            self.data[patient_uuid] = []
        
        vector_id = f"{patient_uuid}_{len(self.data[patient_uuid])}"
        self.data[patient_uuid].append({
            "vector_id": vector_id,
            "score": 1.0,
            "metadata": {
                "patient_uuid": patient_uuid,
                "intent": intent,
                "symptom_category": semantic_context.get("symptom_category", "general"),
                "urgency_level": semantic_context.get("urgency_level", "routine"),
                "requires_specialist": semantic_context.get("requires_specialist", False),
                "estimated_duration": semantic_context.get("estimated_duration", 30),
                "timestamp": timestamp or "2024-01-01 00:00:00"
            }
        })
        return vector_id
    
    def retrieve_patient_history(self, patient_uuid: str, limit: int = 10) -> List[Dict[str, Any]]:
        return self.data.get(patient_uuid, [])[:limit]
    
    def search_similar_contexts(self, query_text: str, patient_uuid: Optional[str] = None, 
                               top_k: int = 5) -> List[Dict[str, Any]]:
        results = []
        if patient_uuid and patient_uuid in self.data:
            results = self.data[patient_uuid][:top_k]
        return results
    
    def delete_patient_metadata(self, patient_uuid: str):
        if patient_uuid in self.data:
            del self.data[patient_uuid]
    
    def get_stats(self) -> Dict[str, Any]:
        return {"total_vectors": sum(len(v) for v in self.data.values()), "dimension": self.dimension, "index_name": self.index_name}


class MockSyntheticStore:
    """Mock synthetic store for testing."""
    
    def __init__(self):
        self.dimension = 384
        self.index_name = "mock-synthetic"
        self.ingested = False
    
    def ingest_synthetic_data(self):
        """Mock ingestion."""
        self.ingested = True
        logger.info("Mock synthetic data ingested")
    
    def search_doctors(self, specialty: str, top_k: int = 5) -> List[Dict[str, Any]]:
        return [
            {
                "score": 0.9,
                "metadata": {
                    "type": "doctor",
                    "specialty": specialty,
                    "content": f"Dr. Mock - Specialist in {specialty}"
                }
            }
        ]
    
    def search_medical_knowledge(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        return [
            {
                "score": 0.85,
                "metadata": {
                    "type": "medical_knowledge",
                    "content": f"Mock medical knowledge about: {query[:50]}"
                }
            }
        ]
    
    def search_similar_cases(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        return [
            {
                "score": 0.8,
                "metadata": {
                    "type": "example_case",
                    "content": f"Mock similar case related to: {query[:50]}"
                }
            }
        ]
    
    def get_stats(self) -> Dict[str, Any]:
        return {"total_vectors": 100, "dimension": self.dimension, "index_name": self.index_name}
