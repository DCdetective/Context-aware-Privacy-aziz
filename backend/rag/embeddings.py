from typing import List, Union
import logging

logger = logging.getLogger(__name__)

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.warning("sentence_transformers not available, using mock embeddings")


class EmbeddingGenerator:
    """
    Generate embeddings for text using sentence transformers.
    Can be replaced with OpenAI embeddings if API key is available.
    """
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize embedding generator.
        
        Args:
            model_name: Name of the sentence transformer model
        """
        self.model_name = model_name
        self.model = None
        self._dimension = 384  # Default dimension for all-MiniLM-L6-v2
        
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                self.model = SentenceTransformer(model_name)
                self._dimension = self.model.get_sentence_embedding_dimension()
                logger.info(f"Embedding generator initialized with model: {model_name}")
            except Exception as e:
                logger.warning(f"Failed to load sentence transformer model: {e}")
                self.model = None
        else:
            logger.info("Using mock embeddings (sentence_transformers not available)")
    
    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Input text
            
        Returns:
            Embedding vector as list of floats
        """
        if self.model is not None:
            embedding = self.model.encode(text, convert_to_numpy=True)
            return embedding.tolist()
        else:
            # Return mock embedding (zeros)
            return [0.0] * self._dimension
    
    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.
        
        Args:
            texts: List of input texts
            
        Returns:
            List of embedding vectors
        """
        if self.model is not None:
            embeddings = self.model.encode(texts, convert_to_numpy=True)
            return embeddings.tolist()
        else:
            # Return mock embeddings (zeros)
            return [[0.0] * self._dimension for _ in texts]
    
    @property
    def dimension(self) -> int:
        """Get embedding dimension."""
        return self._dimension


# Global instance
embedding_generator = EmbeddingGenerator()
