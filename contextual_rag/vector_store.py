"""
Vector Store - ChromaDB Integration

Stores and retrieves embeddings using ChromaDB for semantic search.
"""
import logging
from typing import List, Dict, Any, Optional, Tuple
import chromadb
from chromadb.config import Settings

from .config import Config
from .contextual_enricher import EnrichedChunk


logger = logging.getLogger(__name__)


class VectorStore:
    """ChromaDB vector store for semantic search"""

    def __init__(self):
        """Initialize ChromaDB vector store"""
        # Ensure data directory exists
        Config.ensure_directories()

        # Initialize ChromaDB client with persistent storage
        self.client = chromadb.PersistentClient(
            path=str(Config.CHROMA_DB_PATH),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )

        self.collection = None
        logger.info(f"Initialized ChromaDB at: {Config.CHROMA_DB_PATH}")

    def create_or_get_collection(self, reset: bool = False) -> None:
        """
        Create or get the ChromaDB collection

        Args:
            reset: If True, delete existing collection and create new one
        """
        if reset and self.collection is not None:
            logger.warning(f"Deleting existing collection: {Config.CHROMA_COLLECTION_NAME}")
            self.client.delete_collection(name=Config.CHROMA_COLLECTION_NAME)
            self.collection = None

        try:
            self.collection = self.client.get_or_create_collection(
                name=Config.CHROMA_COLLECTION_NAME,
                metadata={
                    "hnsw:space": Config.CHROMA_DISTANCE_METRIC,
                    "description": "Fitness knowledge base with contextual retrieval"
                }
            )
            logger.info(f"Collection ready: {Config.CHROMA_COLLECTION_NAME}")
            logger.info(f"Collection count: {self.collection.count()} documents")

        except Exception as e:
            logger.error(f"Error creating/getting collection: {e}")
            raise

    def add_chunks(
        self,
        enriched_chunks: List[EnrichedChunk],
        embeddings: List[List[float]]
    ) -> None:
        """
        Add enriched chunks with embeddings to vector store

        Args:
            enriched_chunks: List of enriched chunks
            embeddings: Corresponding embedding vectors
        """
        if self.collection is None:
            raise ValueError("Collection not initialized. Call create_or_get_collection() first.")

        if len(enriched_chunks) != len(embeddings):
            raise ValueError(
                f"Mismatch: {len(enriched_chunks)} chunks but {len(embeddings)} embeddings"
            )

        logger.info(f"Adding {len(enriched_chunks)} chunks to vector store")

        # Prepare data for ChromaDB
        ids = [chunk.chunk_id for chunk in enriched_chunks]
        documents = [chunk.full_text for chunk in enriched_chunks]  # Full text with context
        metadatas = [self._prepare_metadata(chunk) for chunk in enriched_chunks]

        try:
            # Use upsert instead of add to handle both new and existing chunks
            # This allows resuming from checkpoint without duplicate ID errors
            self.collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )

            logger.info(f"Successfully upserted {len(enriched_chunks)} chunks")
            logger.info(f"Total documents in collection: {self.collection.count()}")

        except Exception as e:
            logger.error(f"Error adding chunks to vector store: {e}")
            raise

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 20,
        metadata_filter: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[str, float, str, Dict[str, Any]]]:
        """
        Search for similar chunks using semantic similarity

        Args:
            query_embedding: Query embedding vector
            top_k: Number of results to return
            metadata_filter: Optional metadata filter

        Returns:
            List of tuples: (chunk_id, distance, text, metadata)
        """
        if self.collection is None:
            raise ValueError("Collection not initialized. Call create_or_get_collection() first.")

        logger.debug(f"Searching vector store (top_k={top_k})")

        try:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=metadata_filter
            )

            # Extract results
            chunk_ids = results['ids'][0]
            distances = results['distances'][0]
            documents = results['documents'][0]
            metadatas = results['metadatas'][0]

            search_results = [
                (chunk_id, distance, doc, meta)
                for chunk_id, distance, doc, meta in zip(chunk_ids, distances, documents, metadatas)
            ]

            logger.debug(f"Found {len(search_results)} results")
            return search_results

        except Exception as e:
            logger.error(f"Error searching vector store: {e}")
            raise

    def get_chunk_by_id(self, chunk_id: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Retrieve a chunk by its ID

        Args:
            chunk_id: Chunk ID

        Returns:
            Tuple of (text, metadata) or None if not found
        """
        if self.collection is None:
            raise ValueError("Collection not initialized. Call create_or_get_collection() first.")

        try:
            result = self.collection.get(ids=[chunk_id])

            if result['ids']:
                return result['documents'][0], result['metadatas'][0]
            return None

        except Exception as e:
            logger.error(f"Error retrieving chunk {chunk_id}: {e}")
            raise

    def delete_all(self) -> None:
        """Delete all documents from the collection"""
        if self.collection is None:
            return

        logger.warning("Deleting all documents from collection")
        self.client.delete_collection(name=Config.CHROMA_COLLECTION_NAME)
        self.collection = None

    @staticmethod
    def _prepare_metadata(chunk: EnrichedChunk) -> Dict[str, Any]:
        """
        Prepare metadata for ChromaDB storage

        ChromaDB only supports: str, int, float, bool
        Lists and nested dicts must be converted

        Args:
            chunk: Enriched chunk

        Returns:
            Metadata dictionary compatible with ChromaDB
        """
        metadata = {
            "chunk_id": chunk.chunk_id,
            "topic": chunk.chunk.topic,
            "section_title": chunk.chunk.section_title,
            "subsection": chunk.chunk.subsection or "",
            "section_number": chunk.chunk.section_number or 0,
            "token_count": chunk.token_count,
            "content_type": chunk.chunk.metadata.get("content_type", "general"),
            "has_template": chunk.chunk.metadata.get("has_template", False),
        }

        # Convert lists to comma-separated strings
        training_focus = chunk.chunk.metadata.get("training_focus", [])
        if training_focus:
            metadata["training_focus"] = ",".join(training_focus)

        experience_level = chunk.chunk.metadata.get("experience_level", [])
        if experience_level:
            metadata["experience_level"] = ",".join(experience_level)

        program_structures = chunk.chunk.metadata.get("program_structures", [])
        if program_structures:
            metadata["program_structures"] = ",".join(program_structures)

        return metadata

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the vector store"""
        if self.collection is None:
            return {"status": "not_initialized"}

        return {
            "status": "ready",
            "collection_name": Config.CHROMA_COLLECTION_NAME,
            "total_chunks": self.collection.count(),
            "storage_path": str(Config.CHROMA_DB_PATH),
        }
