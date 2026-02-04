from pinecone import Pinecone, ServerlessSpec
from typing import Dict, Any, List, Optional
import logging
import time

from utils.config import settings
from rag.embeddings import embedding_generator

logger = logging.getLogger(__name__)


class MetadataStore:
    """
    Pinecone store for patient metadata (UUID-linked, non-PII).
    
    PRIVACY GUARANTEE:
    - Stores ONLY UUID-linked semantic context
    - NO patient names, ages, or identifying information
    - Used for retrieving patient history by UUID
    """
    
    def __init__(self):
        """Initialize metadata store."""
        self.pc = Pinecone(api_key=settings.pinecone_api_key)
        self.index_name = settings.pinecone_index_metadata
        self.dimension = embedding_generator.dimension
        
        # Create index if it doesn't exist
        self._create_index_if_needed()
        
        # Get index
        self.index = self.pc.Index(self.index_name)
        
        logger.info(f"Metadata store initialized: {self.index_name}")
    
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
    
    def store_patient_metadata(
        self,
        patient_uuid: str,
        semantic_context: Dict[str, Any],
        intent: str,
        timestamp: Optional[str] = None
    ) -> str:
        """
        Store patient metadata linked to UUID.
        
        Args:
            patient_uuid: Patient UUID (pseudonymized)
            semantic_context: Non-PII semantic medical context
            intent: User intent (appointment, followup, summary)
            timestamp: Optional timestamp
            
        Returns:
            Vector ID
        """
        # Create searchable text from semantic context
        context_text = f"{intent} request. "
        context_text += f"Category: {semantic_context.get('symptom_category', 'general')}. "
        context_text += f"Urgency: {semantic_context.get('urgency_level', 'routine')}. "
        
        logger.info(f"Storing metadata for patient: {patient_uuid}")
        logger.info(f"Context text: {context_text}")
        
        # Generate embedding
        embedding = embedding_generator.generate_embedding(context_text)
        logger.info(f"Generated embedding dimension: {len(embedding)}")
        
        # Verify embedding is not all zeros
        if all(val == 0.0 for val in embedding):
            logger.warning("WARNING: Embedding is all zeros! Check embedding generator.")
        
        # Create metadata (NO PII)
        metadata = {
            "patient_uuid": patient_uuid,
            "intent": intent,
            "symptom_category": semantic_context.get("symptom_category", "general"),
            "urgency_level": semantic_context.get("urgency_level", "routine"),
            "requires_specialist": semantic_context.get("requires_specialist", False),
            "estimated_duration": semantic_context.get("estimated_duration", 30),
            "timestamp": timestamp or time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Generate vector ID
        vector_id = f"{patient_uuid}_{int(time.time() * 1000)}"
        
        # Upsert to Pinecone
        logger.info(f"Upserting vector ID: {vector_id}")
        upsert_response = self.index.upsert(vectors=[(vector_id, embedding, metadata)])
        logger.info(f"Upsert response: {upsert_response}")
        
        # Verify upsert succeeded
        if hasattr(upsert_response, 'upserted_count'):
            logger.info(f"Successfully upserted {upsert_response.upserted_count} vectors")
        
        logger.info(f"✓ Stored metadata for patient UUID: {patient_uuid}")
        return vector_id
    
    def retrieve_patient_history(
        self,
        patient_uuid: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Retrieve patient metadata history by UUID.
        
        Args:
            patient_uuid: Patient UUID
            limit: Maximum number of records to retrieve
            
        Returns:
            List of metadata records
        """
        # Query by patient UUID in metadata
        results = self.index.query(
            vector=[0.0] * self.dimension,  # Dummy vector
            filter={"patient_uuid": {"$eq": patient_uuid}},
            top_k=limit,
            include_metadata=True
        )
        
        history = [
            {
                "vector_id": match.id,
                "score": match.score,
                "metadata": match.metadata
            }
            for match in results.matches
        ]
        
        logger.info(f"Retrieved {len(history)} records for patient UUID: {patient_uuid}")
        return history
    
    def search_similar_contexts(
        self,
        query_text: str,
        patient_uuid: Optional[str] = None,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search for similar medical contexts.
        
        Args:
            query_text: Query text
            patient_uuid: Optional filter by patient UUID
            top_k: Number of results to return
            
        Returns:
            List of similar contexts
        """
        # Generate query embedding
        query_embedding = embedding_generator.generate_embedding(query_text)
        
        # Build filter
        filter_dict = None
        if patient_uuid:
            filter_dict = {"patient_uuid": {"$eq": patient_uuid}}
        
        # Query Pinecone
        results = self.index.query(
            vector=query_embedding,
            filter=filter_dict,
            top_k=top_k,
            include_metadata=True
        )
        
        return [
            {
                "vector_id": match.id,
                "score": match.score,
                "metadata": match.metadata
            }
            for match in results.matches
        ]
    
    def delete_patient_metadata(self, patient_uuid: str):
        """
        Delete all metadata for a patient UUID.
        
        Args:
            patient_uuid: Patient UUID
        """
        # Note: Pinecone doesn't support delete by metadata filter directly
        # Need to retrieve IDs first, then delete
        history = self.retrieve_patient_history(patient_uuid, limit=1000)
        vector_ids = [record["vector_id"] for record in history]
        
        if vector_ids:
            self.index.delete(ids=vector_ids)
            logger.info(f"Deleted {len(vector_ids)} metadata records for patient {patient_uuid}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get store statistics."""
        stats = self.index.describe_index_stats()
        return {
            "total_vectors": stats.total_vector_count,
            "dimension": self.dimension,
            "index_name": self.index_name
        }


# Global instance (will be initialized in main.py)
metadata_store = None
