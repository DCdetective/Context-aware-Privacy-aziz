from pinecone import Pinecone, ServerlessSpec
from typing import Dict, Any, List
import logging
import time

from utils.config import settings
from rag.embeddings import embedding_generator
from rag.synthetic_data import synthetic_data_loader

logger = logging.getLogger(__name__)


class SyntheticStore:
    """
    Pinecone store for synthetic hospital data (RAG knowledge base).
    
    Contains:
    - Doctor information
    - Hospital policies
    - Medical knowledge
    - Example cases
    
    ALL data is synthetic - safe for cloud storage.
    """
    
    def __init__(self):
        """Initialize synthetic data store."""
        self.pc = Pinecone(api_key=settings.pinecone_api_key)
        self.index_name = settings.pinecone_index_synthetic
        self.dimension = embedding_generator.dimension
        
        # Create index if it doesn't exist
        self._create_index_if_needed()
        
        # Get index
        self.index = self.pc.Index(self.index_name)
        
        logger.info(f"Synthetic store initialized: {self.index_name}")
    
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
    
    def ingest_synthetic_data(self):
        """
        Ingest all synthetic data into the vector store.
        Should be run once during setup.
        """
        logger.info("Starting synthetic data ingestion...")
        
        # Get all synthetic documents
        documents = synthetic_data_loader.get_all_synthetic_documents()
        
        # Prepare vectors for upsert
        vectors = []
        for i, doc in enumerate(documents):
            vector_id = f"synthetic_{doc['metadata']['type']}_{i}"
            embedding = embedding_generator.generate_embedding(doc['content'])
            
            vectors.append((
                vector_id,
                embedding,
                {
                    **doc['metadata'],
                    'content': doc['content'][:500]  # Store truncated content in metadata
                }
            ))
        
        # Upsert in batches of 100
        batch_size = 100
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i:i+batch_size]
            self.index.upsert(vectors=batch)
            logger.info(f"Uploaded batch {i//batch_size + 1} ({len(batch)} vectors)")
        
        logger.info(f"Synthetic data ingestion complete: {len(vectors)} documents")
    
    def search_doctors(
        self,
        specialty: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search for doctors by specialty.
        
        Args:
            specialty: Medical specialty
            top_k: Number of results
            
        Returns:
            List of matching doctors
        """
        query_text = f"doctor specializing in {specialty}"
        query_embedding = embedding_generator.generate_embedding(query_text)
        
        results = self.index.query(
            vector=query_embedding,
            filter={"type": {"$eq": "doctor"}},
            top_k=top_k,
            include_metadata=True
        )
        
        return [
            {
                "score": match.score,
                "metadata": match.metadata
            }
            for match in results.matches
        ]
    
    def search_medical_knowledge(
        self,
        query: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search medical knowledge base.
        
        Args:
            query: Search query
            top_k: Number of results
            
        Returns:
            List of relevant knowledge
        """
        query_embedding = embedding_generator.generate_embedding(query)
        
        results = self.index.query(
            vector=query_embedding,
            filter={"type": {"$eq": "medical_knowledge"}},
            top_k=top_k,
            include_metadata=True
        )
        
        return [
            {
                "score": match.score,
                "metadata": match.metadata
            }
            for match in results.matches
        ]
    
    def search_similar_cases(
        self,
        query: str,
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Search for similar example cases.
        
        Args:
            query: Query description
            top_k: Number of results
            
        Returns:
            List of similar cases
        """
        query_embedding = embedding_generator.generate_embedding(query)
        
        results = self.index.query(
            vector=query_embedding,
            filter={"type": {"$eq": "example_case"}},
            top_k=top_k,
            include_metadata=True
        )
        
        return [
            {
                "score": match.score,
                "metadata": match.metadata
            }
            for match in results.matches
        ]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get store statistics."""
        stats = self.index.describe_index_stats()
        return {
            "total_vectors": stats.total_vector_count,
            "dimension": self.dimension,
            "index_name": self.index_name
        }


# Global instance
synthetic_store = None
