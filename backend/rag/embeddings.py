"""
Embedding generation with caching support.

Uses sentence-transformers when available, falls back to hash-based
deterministic embeddings for testing without GPU/model downloads.
"""

from typing import List, Dict
import hashlib
import math
import logging

logger = logging.getLogger(__name__)

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.warning("sentence_transformers not available, using deterministic mock embeddings")


class EmbeddingGenerator:
    """
    Generate embeddings for text using sentence transformers.
    Falls back to deterministic hash-based embeddings if unavailable.
    Includes caching for efficiency.
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
        self._cache: Dict[str, List[float]] = {}
        self._max_cache_size = 10000

        if SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                self.model = SentenceTransformer(model_name)
                self._dimension = self.model.get_sentence_embedding_dimension()
                logger.info(f"Embedding generator initialized with model: {model_name}")
            except Exception as e:
                logger.warning(f"Failed to load sentence transformer model: {e}")
                self.model = None
        else:
            logger.info("Using deterministic hash-based embeddings (sentence_transformers not available)")

    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        Results are cached for efficiency.

        Args:
            text: Input text

        Returns:
            Embedding vector as list of floats
        """
        # Guard against None or empty text
        if text is None or (isinstance(text, str) and text.strip() == ""):
            text = "general medical query"

        # Check cache
        if text in self._cache:
            return self._cache[text]

        if self.model is not None:
            embedding = self.model.encode(text, convert_to_numpy=True)
            result = embedding.tolist()
        else:
            # Deterministic hash-based embedding (not all zeros!)
            result = self._hash_embedding(text)

        # Cache the result
        if len(self._cache) < self._max_cache_size:
            self._cache[text] = result

        return result

    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts (batch).

        Args:
            texts: List of input texts

        Returns:
            List of embedding vectors
        """
        # Guard against None entries in the list
        texts = [t if (t is not None and isinstance(t, str) and t.strip() != "") else "general medical query" for t in texts]

        if self.model is not None:
            # Check which texts are cached
            uncached_indices = []
            uncached_texts = []
            results = [None] * len(texts)

            for i, text in enumerate(texts):
                if text in self._cache:
                    results[i] = self._cache[text]
                else:
                    uncached_indices.append(i)
                    uncached_texts.append(text)

            # Batch encode uncached texts
            if uncached_texts:
                embeddings = self.model.encode(uncached_texts, convert_to_numpy=True)
                for idx, (i, text) in enumerate(zip(uncached_indices, uncached_texts)):
                    emb = embeddings[idx].tolist()
                    results[i] = emb
                    if len(self._cache) < self._max_cache_size:
                        self._cache[text] = emb

            return results
        else:
            return [self.generate_embedding(text) for text in texts]

    def _hash_embedding(self, text: str) -> List[float]:
        """
        Generate a deterministic, non-zero embedding from text using hashing.
        Different texts produce different embeddings with reasonable variance.
        """
        result = []
        for i in range(self._dimension):
            # Create a unique hash for each dimension
            h = hashlib.sha256(f"{text}_{i}".encode()).hexdigest()
            # Convert to float in range [-1, 1]
            val = (int(h[:8], 16) / 0xFFFFFFFF) * 2 - 1
            result.append(val)

        # Normalize to unit length
        norm = math.sqrt(sum(v * v for v in result))
        if norm > 0:
            result = [v / norm for v in result]

        return result

    @property
    def dimension(self) -> int:
        """Get embedding dimension."""
        return self._dimension

    def clear_cache(self):
        """Clear the embedding cache."""
        self._cache.clear()


# Global instance
embedding_generator = EmbeddingGenerator()
