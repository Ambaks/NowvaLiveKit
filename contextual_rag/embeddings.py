"""
Embeddings Module - Voyage AI Integration

Generates embeddings for chunks and queries using Voyage AI's voyage-3 model.
"""
import logging
from typing import List, Optional
import voyageai

from .config import Config
from .contextual_enricher import EnrichedChunk
from .utils import retry_with_backoff, CostTracker, get_token_count


logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    """Generate embeddings using Voyage AI"""

    def __init__(self, cost_tracker: Optional[CostTracker] = None):
        """
        Initialize embedding generator

        Args:
            cost_tracker: Optional cost tracker for monitoring expenses
        """
        self.client = voyageai.Client(api_key=Config.VOYAGE_API_KEY)
        self.cost_tracker = cost_tracker or CostTracker()

    @retry_with_backoff(
        max_retries=Config.MAX_RETRIES,
        initial_delay=Config.RETRY_DELAY,
        backoff_factor=Config.BACKOFF_FACTOR
    )
    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for document chunks

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        logger.info(f"Generating embeddings for {len(texts)} documents")

        # Batch embeddings (max 128 per request)
        all_embeddings = []
        batch_size = Config.EMBEDDING_BATCH_SIZE

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            logger.debug(f"Embedding batch {i//batch_size + 1}: {len(batch)} texts")

            try:
                result = self.client.embed(
                    batch,
                    model=Config.EMBEDDING_MODEL,
                    input_type="document"
                )

                embeddings = result.embeddings
                all_embeddings.extend(embeddings)

                # Calculate cost
                total_tokens = sum(get_token_count(text) for text in batch)
                cost = self._calculate_cost(total_tokens)
                self.cost_tracker.add_cost("embeddings", cost)

                logger.debug(
                    f"Embedded {len(batch)} documents ({total_tokens} tokens, ${cost:.4f})"
                )

            except Exception as e:
                logger.error(f"Error embedding batch {i//batch_size + 1}: {e}")
                raise

        logger.info(f"Generated {len(all_embeddings)} embeddings")
        return all_embeddings

    @retry_with_backoff(
        max_retries=Config.MAX_RETRIES,
        initial_delay=Config.RETRY_DELAY,
        backoff_factor=Config.BACKOFF_FACTOR
    )
    async def embed_query(self, query: str) -> List[float]:
        """
        Generate embedding for a search query

        Args:
            query: Query string

        Returns:
            Embedding vector
        """
        logger.debug(f"Embedding query: {query[:100]}...")

        try:
            result = self.client.embed(
                [query],
                model=Config.EMBEDDING_MODEL,
                input_type="query"
            )

            embedding = result.embeddings[0]

            # Calculate cost
            tokens = get_token_count(query)
            cost = self._calculate_cost(tokens)
            self.cost_tracker.add_cost("embeddings", cost)

            logger.debug(f"Query embedded ({tokens} tokens, ${cost:.6f})")

            return embedding

        except Exception as e:
            logger.error(f"Error embedding query: {e}")
            raise

    async def embed_enriched_chunks(
        self,
        enriched_chunks: List[EnrichedChunk]
    ) -> List[List[float]]:
        """
        Generate embeddings for enriched chunks (context + original text)

        Args:
            enriched_chunks: List of enriched chunks

        Returns:
            List of embedding vectors
        """
        logger.info(f"Generating embeddings for {len(enriched_chunks)} enriched chunks")

        # Extract full text (context + original chunk)
        texts = [chunk.full_text for chunk in enriched_chunks]

        # Generate embeddings
        embeddings = await self.embed_documents(texts)

        logger.info(f"Generated {len(embeddings)} embeddings for enriched chunks")
        return embeddings

    @staticmethod
    def _calculate_cost(tokens: int) -> float:
        """Calculate cost for Voyage AI embedding"""
        # Voyage-3 pricing: $0.13 per 1M tokens
        return tokens * (0.13 / 1_000_000)
