"""
Script to ingest synthetic data into Pinecone.
Run this once to populate the knowledge base.
"""
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from vector_store.synthetic_store import SyntheticStore
from rag.synthetic_data import synthetic_data_loader
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def ingest_data():
    """Ingest all synthetic data into Pinecone."""
    logger.info("=" * 60)
    logger.info("STARTING SYNTHETIC DATA INGESTION")
    logger.info("=" * 60)
    
    # Initialize store
    store = SyntheticStore()
    
    # Ingest data
    store.ingest_synthetic_data()
    
    # Verify ingestion
    stats = store.get_stats()
    logger.info("=" * 60)
    logger.info("INGESTION COMPLETE")
    logger.info(f"Total vectors: {stats['total_vectors']}")
    logger.info("=" * 60)
    
    return stats


if __name__ == "__main__":
    ingest_data()
