"""
Hybrid Retriever - Semantic + BM25 with Reciprocal Rank Fusion (RRF)

Combines semantic search (ChromaDB) and lexical search (BM25) using RRF
to get the best of both approaches.
"""
import logging
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass

from .config import Config
from .vector_store import VectorStore
from .bm25_index import BM25Index
from .embeddings import EmbeddingGenerator
from .utils import CostTracker


logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    """Represents a chunk retrieved from hybrid search"""
    chunk_id: str
    text: str
    metadata: Dict[str, Any]
    score: float  # RRF score
    semantic_rank: Optional[int] = None
    bm25_rank: Optional[int] = None

    def __repr__(self):
        return f"RetrievedChunk(id={self.chunk_id}, score={self.score:.4f})"


class HybridRetriever:
    """Hybrid retrieval using semantic + BM25 search with RRF"""

    def __init__(
        self,
        vector_store: VectorStore,
        bm25_index: BM25Index,
        embedding_generator: EmbeddingGenerator,
        cost_tracker: Optional[CostTracker] = None
    ):
        """
        Initialize hybrid retriever

        Args:
            vector_store: ChromaDB vector store
            bm25_index: BM25 index
            embedding_generator: Embedding generator for queries
            cost_tracker: Optional cost tracker
        """
        self.vector_store = vector_store
        self.bm25_index = bm25_index
        self.embedding_generator = embedding_generator
        self.cost_tracker = cost_tracker or CostTracker()

    async def retrieve(
        self,
        query: str,
        top_k: int = 20,
        semantic_weight: float = Config.SEMANTIC_WEIGHT,
        bm25_weight: float = Config.BM25_WEIGHT,
        metadata_filter: Optional[Dict[str, Any]] = None
    ) -> List[RetrievedChunk]:
        """
        Hybrid retrieval with RRF fusion

        Args:
            query: Search query
            top_k: Number of results to return after fusion
            semantic_weight: Weight for semantic search scores
            bm25_weight: Weight for BM25 scores
            metadata_filter: Optional metadata filter for semantic search

        Returns:
            List of retrieved chunks sorted by RRF score
        """
        logger.info(f"Hybrid retrieval for query: {query[:100]}...")
        logger.debug(f"Weights: semantic={semantic_weight}, bm25={bm25_weight}")

        # 1. Semantic search
        logger.debug(f"Performing semantic search (top_k={Config.SEMANTIC_TOP_K})")
        query_embedding = await self.embedding_generator.embed_query(query)
        semantic_results = self.vector_store.search(
            query_embedding=query_embedding,
            top_k=Config.SEMANTIC_TOP_K,
            metadata_filter=metadata_filter
        )

        # 2. BM25 search
        logger.debug(f"Performing BM25 search (top_k={Config.BM25_TOP_K})")
        bm25_results = self.bm25_index.search(
            query=query,
            top_k=Config.BM25_TOP_K
        )

        # 3. Apply Reciprocal Rank Fusion (RRF)
        logger.debug("Applying Reciprocal Rank Fusion")
        fused_results = self._reciprocal_rank_fusion(
            semantic_results=semantic_results,
            bm25_results=bm25_results,
            semantic_weight=semantic_weight,
            bm25_weight=bm25_weight
        )

        # 4. Return top-k
        top_results = fused_results[:top_k]

        logger.info(f"Hybrid retrieval returned {len(top_results)} chunks")
        if top_results:
            logger.debug(f"Top RRF score: {top_results[0].score:.4f}")
            logger.debug(f"Bottom RRF score: {top_results[-1].score:.4f}")

        return top_results

    def _reciprocal_rank_fusion(
        self,
        semantic_results: List[Tuple[str, float, str, Dict[str, Any]]],
        bm25_results: List[Tuple[str, float, str]],
        semantic_weight: float,
        bm25_weight: float
    ) -> List[RetrievedChunk]:
        """
        Apply Reciprocal Rank Fusion to combine semantic and BM25 results

        RRF formula: score(d) = sum over retrievers of: weight / (k + rank(d))
        where k = 60 (standard constant)

        Args:
            semantic_results: Results from semantic search
            bm25_results: Results from BM25 search
            semantic_weight: Weight for semantic scores
            bm25_weight: Weight for BM25 scores

        Returns:
            List of fused results sorted by RRF score
        """
        k = Config.RRF_K
        chunk_scores: Dict[str, Dict[str, Any]] = {}

        # Process semantic results
        for rank, (chunk_id, distance, text, metadata) in enumerate(semantic_results, 1):
            if chunk_id not in chunk_scores:
                chunk_scores[chunk_id] = {
                    "text": text,
                    "metadata": metadata,
                    "rrf_score": 0.0,
                    "semantic_rank": None,
                    "bm25_rank": None
                }

            # RRF contribution from semantic search
            rrf_contribution = semantic_weight / (k + rank)
            chunk_scores[chunk_id]["rrf_score"] += rrf_contribution
            chunk_scores[chunk_id]["semantic_rank"] = rank

        # Process BM25 results
        for rank, (chunk_id, score, text) in enumerate(bm25_results, 1):
            if chunk_id not in chunk_scores:
                # Need to fetch metadata from vector store
                result = self.vector_store.get_chunk_by_id(chunk_id)
                if result:
                    text_from_store, metadata = result
                    chunk_scores[chunk_id] = {
                        "text": text_from_store,
                        "metadata": metadata,
                        "rrf_score": 0.0,
                        "semantic_rank": None,
                        "bm25_rank": None
                    }
                else:
                    # Chunk not in vector store, use BM25 text
                    chunk_scores[chunk_id] = {
                        "text": text,
                        "metadata": {},
                        "rrf_score": 0.0,
                        "semantic_rank": None,
                        "bm25_rank": None
                    }

            # RRF contribution from BM25
            rrf_contribution = bm25_weight / (k + rank)
            chunk_scores[chunk_id]["rrf_score"] += rrf_contribution
            chunk_scores[chunk_id]["bm25_rank"] = rank

        # Convert to RetrievedChunk objects and sort by RRF score
        retrieved_chunks = [
            RetrievedChunk(
                chunk_id=chunk_id,
                text=data["text"],
                metadata=data["metadata"],
                score=data["rrf_score"],
                semantic_rank=data["semantic_rank"],
                bm25_rank=data["bm25_rank"]
            )
            for chunk_id, data in chunk_scores.items()
        ]

        retrieved_chunks.sort(key=lambda x: x.score, reverse=True)

        logger.debug(f"RRF fused {len(retrieved_chunks)} unique chunks")
        return retrieved_chunks
