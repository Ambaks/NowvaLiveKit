"""
Contextual Enricher - Anthropic's Contextual Retrieval

Applies the exact Anthropic contextual retrieval prompt to generate
succinct context that situates each chunk within the full document.

This approach reduces retrieval failures by 67% according to Anthropic's research.
"""
import logging
from typing import List, Optional
from dataclasses import dataclass, replace
import anthropic

from .config import Config
from .propositional_chunker import SemanticChunk
from .document_processor import ParsedDocument
from .utils import retry_with_backoff, CostTracker


logger = logging.getLogger(__name__)


@dataclass
class EnrichedChunk:
    """Semantic chunk with contextual description prepended"""
    chunk: SemanticChunk
    contextual_description: str
    full_text: str  # context + "\n\n" + original chunk text

    @property
    def chunk_id(self) -> str:
        return self.chunk.chunk_id

    @property
    def token_count(self) -> int:
        from .utils import get_token_count
        return get_token_count(self.full_text)

    def to_dict(self):
        """Convert to dictionary for serialization"""
        return {
            **self.chunk.to_dict(),
            "contextual_description": self.contextual_description,
            "full_text": self.full_text
        }


class ContextualEnricher:
    """Apply Anthropic's contextual retrieval to chunks"""

    # EXACT Anthropic prompt - DO NOT MODIFY
    CONTEXTUAL_PROMPT_TEMPLATE = """<document>
{whole_document}
</document>

Here is the chunk we want to situate within the whole document
<chunk>
{chunk_content}
</chunk>

Please give a short succinct context to situate this chunk within the overall document for the purposes of improving search retrieval of the chunk. Answer only with the succinct context and nothing else."""

    def __init__(self, cost_tracker: Optional[CostTracker] = None):
        """
        Initialize contextual enricher

        Args:
            cost_tracker: Optional cost tracker for monitoring expenses
        """
        self.client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
        self.cost_tracker = cost_tracker or CostTracker()

    @retry_with_backoff(
        max_retries=Config.MAX_RETRIES,
        initial_delay=Config.RETRY_DELAY,
        backoff_factor=Config.BACKOFF_FACTOR
    )
    async def enrich_chunk(
        self,
        chunk: SemanticChunk,
        full_document: str,
        use_cache: bool = True
    ) -> EnrichedChunk:
        """
        Generate contextual description for a single chunk using Anthropic's prompt

        Args:
            chunk: Semantic chunk to enrich
            full_document: Full document text (will be cached by Anthropic)
            use_cache: Whether to use prompt caching (default: True)

        Returns:
            Enriched chunk with contextual description
        """
        # Build prompt using EXACT Anthropic template
        prompt = self.CONTEXTUAL_PROMPT_TEMPLATE.format(
            whole_document=full_document,
            chunk_content=chunk.text
        )

        try:
            # Use prompt caching for the document portion
            if use_cache:
                # System message with cached document
                system_content = [
                    {
                        "type": "text",
                        "text": f"<document>\n{full_document}\n</document>",
                        "cache_control": {"type": "ephemeral"}
                    }
                ]

                # User message with chunk
                user_message = f"""Here is the chunk we want to situate within the whole document
<chunk>
{chunk.text}
</chunk>

Please give a short succinct context to situate this chunk within the overall document for the purposes of improving search retrieval of the chunk. Answer only with the succinct context and nothing else."""

                message = self.client.messages.create(
                    model=Config.CONTEXTUALIZATION_MODEL,
                    max_tokens=1000,
                    system=system_content,
                    messages=[{"role": "user", "content": user_message}]
                )
            else:
                # No caching - single message
                message = self.client.messages.create(
                    model=Config.CONTEXTUALIZATION_MODEL,
                    max_tokens=1000,
                    messages=[{"role": "user", "content": prompt}]
                )

            # Track cost
            input_tokens = message.usage.input_tokens
            output_tokens = message.usage.output_tokens
            cached_tokens = getattr(message.usage, 'cache_read_input_tokens', 0)

            cost = self._calculate_cost(input_tokens, output_tokens, cached_tokens)
            self.cost_tracker.add_cost("contextualization", cost)

            # Log cache performance
            if cached_tokens > 0:
                cache_savings_pct = (cached_tokens / (input_tokens + cached_tokens)) * 100
                logger.debug(
                    f"Contextualization (CACHE HIT): {input_tokens} input + "
                    f"{cached_tokens} cached + {output_tokens} output tokens "
                    f"({cache_savings_pct:.0f}% cached, ${cost:.4f})"
                )
            else:
                logger.debug(
                    f"Contextualization: {input_tokens} input + {output_tokens} output tokens "
                    f"(${cost:.4f})"
                )

            # Extract contextual description
            contextual_description = message.content[0].text.strip()

            # Create enriched chunk with context prepended
            full_text = f"{contextual_description}\n\n{chunk.text}"

            return EnrichedChunk(
                chunk=chunk,
                contextual_description=contextual_description,
                full_text=full_text
            )

        except Exception as e:
            logger.error(f"Error enriching chunk {chunk.chunk_id}: {e}")
            raise

    async def enrich_chunks(
        self,
        chunks: List[SemanticChunk],
        document: ParsedDocument
    ) -> List[EnrichedChunk]:
        """
        Enrich all chunks with contextual descriptions

        Uses prompt caching to dramatically reduce costs - the full document
        is cached after the first API call, resulting in 90% cost savings.

        Args:
            chunks: List of semantic chunks to enrich
            document: Full parsed document (for caching)

        Returns:
            List of enriched chunks
        """
        logger.info(f"Enriching {len(chunks)} chunks with contextual descriptions")
        logger.info(f"Document: {document.title} ({document.total_tokens:,} tokens)")
        logger.info("Using Anthropic's prompt caching for 90% cost savings")

        enriched_chunks = []
        total_cost_before = self.cost_tracker.costs["contextualization"]

        for i, chunk in enumerate(chunks, 1):
            logger.info(f"Enriching chunk {i}/{len(chunks)}: {chunk.topic}")

            try:
                enriched = await self.enrich_chunk(
                    chunk=chunk,
                    full_document=document.full_text,
                    use_cache=True  # Always use caching
                )
                enriched_chunks.append(enriched)

                # Log first enrichment as example
                if i == 1:
                    logger.info(f"\nExample enrichment:")
                    logger.info(f"Original chunk ({chunk.token_count} tokens):")
                    logger.info(f"  {chunk.text[:200]}...")
                    logger.info(f"\nContextual description:")
                    logger.info(f"  {enriched.contextual_description}")
                    logger.info(f"\nFull enriched text ({enriched.token_count} tokens)\n")

            except Exception as e:
                logger.error(f"Failed to enrich chunk {chunk.chunk_id}: {e}", exc_info=True)
                # Skip this chunk rather than failing entire batch
                continue

        total_cost = self.cost_tracker.costs["contextualization"] - total_cost_before

        logger.info(f"\n{'='*60}")
        logger.info(f"Contextual Enrichment Complete")
        logger.info(f"{'='*60}")
        logger.info(f"Chunks enriched: {len(enriched_chunks)}/{len(chunks)}")
        logger.info(f"Total cost: ${total_cost:.4f}")
        logger.info(f"Avg cost per chunk: ${total_cost/len(enriched_chunks):.4f}")
        logger.info(f"{'='*60}\n")

        return enriched_chunks

    @staticmethod
    def _calculate_cost(input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> float:
        """Calculate cost for Claude API call with caching"""
        # Claude 3.5 Haiku pricing
        input_cost = input_tokens * (1.00 / 1_000_000)
        output_cost = output_tokens * (5.00 / 1_000_000)
        cached_cost = cached_tokens * (0.10 / 1_000_000)  # 90% discount

        return input_cost + output_cost + cached_cost
