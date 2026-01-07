"""
Reranker - Cohere Reranking

Uses Cohere's rerank-v3.5 model to refine and reorder retrieved chunks
for maximum relevance.
"""
import logging
from typing import List, Optional
import cohere

from .config import Config
from .hybrid_retriever import RetrievedChunk
from .utils import retry_with_backoff, CostTracker


logger = logging.getLogger(__name__)


class Reranker:
    """Cohere reranking for retrieved chunks"""

    def __init__(self, cost_tracker: Optional[CostTracker] = None):
        """
        Initialize reranker

        Args:
            cost_tracker: Optional cost tracker for monitoring expenses
        """
        self.client = cohere.Client(api_key=Config.COHERE_API_KEY)
        self.cost_tracker = cost_tracker or CostTracker()

    @retry_with_backoff(
        max_retries=Config.MAX_RETRIES,
        initial_delay=Config.RETRY_DELAY,
        backoff_factor=Config.BACKOFF_FACTOR
    )
    async def rerank(
        self,
        query: str,
        chunks: List[RetrievedChunk],
        top_n: int = Config.RERANK_TOP_N
    ) -> List[RetrievedChunk]:
        """
        Rerank retrieved chunks using Cohere's rerank API

        Args:
            query: Original search query
            chunks: List of retrieved chunks to rerank
            top_n: Number of top results to return

        Returns:
            Reranked list of chunks (top_n most relevant)
        """
        if not chunks:
            return []

        logger.info(f"Reranking {len(chunks)} chunks (returning top {top_n})")

        # Prepare documents for reranking
        documents = [chunk.text for chunk in chunks]

        try:
            # Call Cohere rerank API
            response = self.client.rerank(
                model=Config.RERANK_MODEL,
                query=query,
                documents=documents,
                top_n=top_n,
                return_documents=False  # We already have the documents
            )

            # Track cost
            cost = self._calculate_cost(len(chunks))
            self.cost_tracker.add_cost("reranking", cost)

            logger.info(f"Reranking cost: ${cost:.4f}")

            # Extract reranked chunks
            reranked_chunks = []
            for result in response.results:
                original_chunk = chunks[result.index]

                # Update score to Cohere's relevance score
                reranked_chunk = RetrievedChunk(
                    chunk_id=original_chunk.chunk_id,
                    text=original_chunk.text,
                    metadata=original_chunk.metadata,
                    score=result.relevance_score,  # Cohere's relevance score
                    semantic_rank=original_chunk.semantic_rank,
                    bm25_rank=original_chunk.bm25_rank
                )
                reranked_chunks.append(reranked_chunk)

            logger.info(f"Reranked to {len(reranked_chunks)} top chunks")
            if reranked_chunks:
                logger.debug(f"Top relevance score: {reranked_chunks[0].score:.4f}")
                logger.debug(f"Bottom relevance score: {reranked_chunks[-1].score:.4f}")

            return reranked_chunks

        except Exception as e:
            logger.error(f"Error during reranking: {e}")
            # Fallback: return original chunks (top_n)
            logger.warning(f"Falling back to original ranking")
            return chunks[:top_n]

    @staticmethod
    def _calculate_cost(num_documents: int) -> float:
        """
        Calculate cost for Cohere reranking

        Cohere pricing: $2.00 per 1,000 searches
        Each search can rerank multiple documents

        Args:
            num_documents: Number of documents being reranked

        Returns:
            Cost in USD
        """
        # Cohere charges per search, not per document
        cost_per_search = 2.00 / 1000
        return cost_per_search
