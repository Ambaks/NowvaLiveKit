"""
Configuration for Contextual RAG System
"""
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Centralized configuration for the RAG system"""

    # ===== API Keys =====
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    VOYAGE_API_KEY: str = os.getenv("VOYAGE_API_KEY", "")
    COHERE_API_KEY: str = os.getenv("COHERE_API_KEY", "")

    # ===== Model Configuration =====
    # Contextualization
    CONTEXTUALIZATION_MODEL: str = "claude-3-5-haiku-20241022"

    # Propositional chunking
    PROPOSITION_EXTRACTION_MODEL: str = "claude-3-5-haiku-20241022"
    PROPOSITION_GROUPING_MODEL: str = "claude-3-5-haiku-20241022"

    # Embeddings
    EMBEDDING_MODEL: str = "voyage-3"
    EMBEDDING_BATCH_SIZE: int = 128

    # Reranking
    RERANK_MODEL: str = "rerank-v3.5"

    # ===== Chunking Configuration =====
    MIN_CHUNK_TOKENS: int = 200
    MAX_CHUNK_TOKENS: int = 800
    TARGET_CHUNK_TOKENS: int = 500

    # ===== Retrieval Configuration =====
    # Hybrid search
    SEMANTIC_TOP_K: int = 20
    BM25_TOP_K: int = 20
    RRF_K: int = 60  # Standard RRF constant

    # Weights for hybrid search
    SEMANTIC_WEIGHT: float = 1.0
    BM25_WEIGHT: float = 1.0

    # Reranking
    RERANK_TOP_N: int = 10

    # Final output
    FINAL_CHUNKS_MIN: int = 3
    FINAL_CHUNKS_MAX: int = 10
    MAX_TOKENS_BUDGET: int = 2000

    # ===== Storage Paths =====
    BASE_DIR: Path = Path(__file__).parent
    DATA_DIR: Path = BASE_DIR / "data"
    CHROMA_DB_PATH: Path = DATA_DIR / "chroma_db"
    BM25_INDEX_PATH: Path = DATA_DIR / "bm25_index.pkl"
    CHUNKS_METADATA_PATH: Path = DATA_DIR / "chunks_metadata.json"
    CHECKPOINT_PATH: Path = DATA_DIR / "ingestion_checkpoint.pkl"

    # ===== ChromaDB Configuration =====
    CHROMA_COLLECTION_NAME: str = "fitness_knowledge_base"
    CHROMA_DISTANCE_METRIC: str = "cosine"

    # ===== Rate Limiting & Retry =====
    MAX_RETRIES: int = 3
    RETRY_DELAY: float = 1.0  # seconds
    BACKOFF_FACTOR: float = 2.0

    # ===== Logging =====
    LOG_LEVEL: str = os.getenv("RAG_LOG_LEVEL", "INFO")
    LOG_COSTS: bool = True

    @classmethod
    def validate(cls) -> None:
        """Validate that all required API keys are set"""
        required_keys = {
            "ANTHROPIC_API_KEY": cls.ANTHROPIC_API_KEY,
            "VOYAGE_API_KEY": cls.VOYAGE_API_KEY,
            "COHERE_API_KEY": cls.COHERE_API_KEY,
        }

        missing = [key for key, value in required_keys.items() if not value]
        if missing:
            raise ValueError(
                f"Missing required API keys: {', '.join(missing)}. "
                f"Please set them in your .env file."
            )

    @classmethod
    def ensure_directories(cls) -> None:
        """Ensure all required directories exist"""
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.CHROMA_DB_PATH.mkdir(parents=True, exist_ok=True)
