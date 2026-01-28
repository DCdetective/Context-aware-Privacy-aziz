from typing import List, Dict, Optional, Any
import logging
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class MockSemanticStore:
    """
    Mock semantic store for testing without Pinecone API.
    Simulates Pinecone functionality using in-memory storage.
    """
    
    def __init__(self):
        """Initialize mock store."""
        self.storage: Dict[str, Dict[str, Any]] = {}
        self.dimension = 384
        logger.info("Mock Semantic Store initialized (testing mode)")
    
    def store_semantic_anchor(
        self,
        patient_uuid: str,
        anchor_type: str,
        semantic_data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Store semantic anchor in memory."""
        # Privacy validation - check if forbidden fields exist as keys
        forbidden_fields = ['name', 'patient_name', 'age', 'gender', 'ssn', 'dob']
        
        for field in forbidden_fields:
            # Check if field exists as a key in semantic_data (case-insensitive)
            if field in [k.lower() for k in semantic_data.keys()]:
                raise ValueError(f"Privacy violation: Cannot store PII field '{field}' in semantic store")
        
        anchor_id = f"{patient_uuid}_{anchor_type}_{datetime.utcnow().timestamp()}"
        
        self.storage[anchor_id] = {
            "patient_uuid": patient_uuid,
            "anchor_type": anchor_type,
            "semantic_data": semantic_data,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return anchor_id
    
    def retrieve_semantic_anchors(
        self,
        patient_uuid: str,
        anchor_type: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Retrieve anchors from memory."""
        results = []
        
        for anchor_id, data in self.storage.items():
            if data["patient_uuid"] == patient_uuid:
                if anchor_type is None or data["anchor_type"] == anchor_type:
                    results.append({
                        "anchor_id": anchor_id,
                        **data,
                        "score": 1.0
                    })
        
        return results[:limit]
    
    def search_similar_semantics(
        self,
        query_text: str,
        patient_uuid: Optional[str] = None,
        anchor_type: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Search for similar semantics (simplified)."""
        results = []
        
        for anchor_id, data in self.storage.items():
            match = True
            if patient_uuid and data["patient_uuid"] != patient_uuid:
                match = False
            if anchor_type and data["anchor_type"] != anchor_type:
                match = False
            
            if match:
                results.append({
                    "anchor_id": anchor_id,
                    **data,
                    "similarity_score": 0.85
                })
        
        return results[:limit]
    
    def delete_patient_anchors(self, patient_uuid: str) -> int:
        """Delete patient anchors from memory."""
        to_delete = [
            aid for aid, data in self.storage.items()
            if data["patient_uuid"] == patient_uuid
        ]
        
        for aid in to_delete:
            del self.storage[aid]
        
        return len(to_delete)
    
    def get_store_stats(self) -> Dict[str, Any]:
        """Get store statistics."""
        return {
            "index_name": "mock-store",
            "dimension": self.dimension,
            "total_vectors": len(self.storage),
            "contains_pii": False
        }
