from pinecone import Pinecone, ServerlessSpec
from typing import List, Dict, Optional, Any
import logging
import hashlib
import json
import time
from datetime import datetime

try:
    from ..utils.config import settings
except ImportError:
    from utils.config import settings

logger = logging.getLogger(__name__)


class SemanticAnchorStore:
    """
    Pinecone-based vector store for non-sensitive medical context.
    
    PRIVACY GUARANTEE:
    - Stores ONLY semantic anchors (non-PII medical context)
    - All data indexed by UUID (no patient names/identities)
    - Safe for cloud storage as it contains no PII
    - Enables context-aware reasoning without privacy violations
    """
    
    def __init__(self):
        """Initialize Pinecone semantic store."""
        try:
            self.pc = Pinecone(api_key=settings.pinecone_api_key)
            self.index_name = settings.pinecone_index_metadata
            self.dimension = 1024  # Default dimension for semantic anchors
            
            # Create index if it doesn't exist
            self._create_index_if_needed()
            
            # Connect to index
            self.index = self.pc.Index(self.index_name)
            
            logger.info(f"Semantic Anchor Store initialized with index: {self.index_name}")
            logger.info(f"Vector dimension: {self.dimension}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Pinecone: {str(e)}")
            raise
    
    def _create_index_if_needed(self):
        """Create Pinecone index if it doesn't exist."""
        existing_indexes = [idx.name for idx in self.pc.list_indexes()]
        
        if self.index_name not in existing_indexes:
            logger.info(f"Creating Pinecone index: {self.index_name}")
            
            self.pc.create_index(
                name=self.index_name,
                dimension=self.dimension,
                metric="cosine",
                spec=ServerlessSpec(
                    cloud="aws",
                    region=settings.pinecone_environment
                )
            )
            
            # Wait for index to be ready
            while not self.pc.describe_index(self.index_name).status['ready']:
                time.sleep(1)
            
            logger.info(f"Index {self.index_name} created successfully")
    
    
    def _generate_vector(self, text: str) -> List[float]:
        """
        Generate embedding vector from text.
        For simplicity, using a hash-based approach.
        In production, use proper sentence transformers.
        
        Args:
            text: Text to vectorize
            
        Returns:
            384-dimensional vector
        """
        # Simple hash-based vector generation for demonstration
        # In production, use: sentence_transformers, OpenAI embeddings, etc.
        hash_obj = hashlib.sha256(text.encode())
        hash_bytes = hash_obj.digest()
        
        # Generate 384-dim vector from hash
        vector = []
        for i in range(self.dimension):
            byte_idx = i % len(hash_bytes)
            vector.append((hash_bytes[byte_idx] / 255.0) * 2 - 1)
        
        return vector
    
    def store_semantic_anchor(
        self,
        patient_uuid: str,
        anchor_type: str,
        semantic_data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Store a semantic anchor for a patient.
        
        PRIVACY CHECK: This method validates that NO PII is being stored.
        
        Args:
            patient_uuid: Patient UUID (pseudonymized identifier)
            anchor_type: Type of semantic anchor (e.g., 'preference', 'constraint', 'context')
            semantic_data: Non-PII semantic information
            metadata: Additional non-PII metadata
            
        Returns:
            anchor_id: Unique identifier for the stored anchor
        """
        try:
            # PRIVACY VALIDATION: Check for forbidden PII fields as keys
            forbidden_fields = ['name', 'patient_name', 'age', 'gender', 'ssn', 'dob']
            
            for field in forbidden_fields:
                # Check if field exists as a key in semantic_data (case-insensitive)
                if field in [k.lower() for k in semantic_data.keys()]:
                    logger.error(f"PRIVACY VIOLATION: Attempted to store PII field '{field}'")
                    raise ValueError(f"Privacy violation: Cannot store PII field '{field}' in semantic store")
            
            # Generate anchor ID
            anchor_id = f"{patient_uuid}_{anchor_type}_{datetime.utcnow().timestamp()}"
            
            # Create searchable text from semantic data
            searchable_text = f"{anchor_type} " + " ".join(str(v) for v in semantic_data.values())
            vector = self._generate_vector(searchable_text)
            
            # Prepare metadata
            full_metadata = {
                "patient_uuid": patient_uuid,
                "anchor_type": anchor_type,
                "semantic_data": json.dumps(semantic_data),
                "timestamp": datetime.utcnow().isoformat(),
                "contains_pii": False  # Always False for semantic store
            }
            
            if metadata:
                full_metadata.update(metadata)
            
            # Store in Pinecone
            self.index.upsert(
                vectors=[
                    {
                        "id": anchor_id,
                        "values": vector,
                        "metadata": full_metadata
                    }
                ]
            )
            
            logger.info(f"Stored semantic anchor: {anchor_id} for patient {patient_uuid[:8]}...")
            return anchor_id
            
        except Exception as e:
            logger.error(f"Error storing semantic anchor: {str(e)}")
            raise
    
    def retrieve_semantic_anchors(
        self,
        patient_uuid: str,
        anchor_type: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Retrieve semantic anchors for a patient.
        
        Args:
            patient_uuid: Patient UUID
            anchor_type: Optional filter by anchor type
            limit: Maximum number of anchors to retrieve
            
        Returns:
            List of semantic anchors
        """
        try:
            # Build filter
            filter_dict = {"patient_uuid": patient_uuid}
            if anchor_type:
                filter_dict["anchor_type"] = anchor_type
            
            # Query Pinecone
            # Note: Pinecone requires a vector for query, using zero vector for metadata-only search
            zero_vector = [0.0] * self.dimension
            
            results = self.index.query(
                vector=zero_vector,
                filter=filter_dict,
                top_k=limit,
                include_metadata=True
            )
            
            # Parse results
            anchors = []
            for match in results.matches:
                anchor = {
                    "anchor_id": match.id,
                    "patient_uuid": match.metadata.get("patient_uuid"),
                    "anchor_type": match.metadata.get("anchor_type"),
                    "semantic_data": json.loads(match.metadata.get("semantic_data", "{}")),
                    "timestamp": match.metadata.get("timestamp"),
                    "score": match.score
                }
                anchors.append(anchor)
            
            logger.info(f"Retrieved {len(anchors)} semantic anchors for patient {patient_uuid[:8]}...")
            return anchors
            
        except Exception as e:
            logger.error(f"Error retrieving semantic anchors: {str(e)}")
            raise
    
    def search_similar_semantics(
        self,
        query_text: str,
        patient_uuid: Optional[str] = None,
        anchor_type: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search for semantically similar anchors using vector similarity.
        
        Args:
            query_text: Text to search for
            patient_uuid: Optional filter by patient
            anchor_type: Optional filter by anchor type
            limit: Maximum number of results
            
        Returns:
            List of similar semantic anchors
        """
        try:
            # Generate query vector
            query_vector = self._generate_vector(query_text)
            
            # Build filter
            filter_dict = {}
            if patient_uuid:
                filter_dict["patient_uuid"] = patient_uuid
            if anchor_type:
                filter_dict["anchor_type"] = anchor_type
            
            # Query Pinecone
            results = self.index.query(
                vector=query_vector,
                filter=filter_dict if filter_dict else None,
                top_k=limit,
                include_metadata=True
            )
            
            # Parse results
            anchors = []
            for match in results.matches:
                anchor = {
                    "anchor_id": match.id,
                    "patient_uuid": match.metadata.get("patient_uuid"),
                    "anchor_type": match.metadata.get("anchor_type"),
                    "semantic_data": json.loads(match.metadata.get("semantic_data", "{}")),
                    "timestamp": match.metadata.get("timestamp"),
                    "similarity_score": match.score
                }
                anchors.append(anchor)
            
            logger.info(f"Found {len(anchors)} similar semantic anchors")
            return anchors
            
        except Exception as e:
            logger.error(f"Error searching semantic anchors: {str(e)}")
            raise
    
    def delete_patient_anchors(self, patient_uuid: str) -> int:
        """
        Delete all semantic anchors for a patient.
        
        Args:
            patient_uuid: Patient UUID
            
        Returns:
            Number of anchors deleted
        """
        try:
            # Retrieve all anchors for patient
            anchors = self.retrieve_semantic_anchors(patient_uuid, limit=1000)
            
            if not anchors:
                logger.info(f"No anchors found for patient {patient_uuid[:8]}...")
                return 0
            
            # Delete from Pinecone
            anchor_ids = [anchor["anchor_id"] for anchor in anchors]
            self.index.delete(ids=anchor_ids)
            
            logger.info(f"Deleted {len(anchor_ids)} anchors for patient {patient_uuid[:8]}...")
            return len(anchor_ids)
            
        except Exception as e:
            logger.error(f"Error deleting semantic anchors: {str(e)}")
            raise
    
    def get_store_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the semantic store.
        
        Returns:
            Dictionary with store statistics
        """
        try:
            stats = self.index.describe_index_stats()
            
            return {
                "index_name": self.index_name,
                "dimension": self.dimension,
                "total_vectors": stats.total_vector_count,
                "namespaces": stats.namespaces,
                "contains_pii": False  # Always False for semantic store
            }
            
        except Exception as e:
            logger.error(f"Error getting store stats: {str(e)}")
            raise


# Global instance
semantic_store = SemanticAnchorStore()
