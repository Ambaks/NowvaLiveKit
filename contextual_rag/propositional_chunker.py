"""
Propositional Chunker - LLM-based intelligent chunking

Two-stage process:
1. Extract atomic propositions from document sections
2. Group propositions into semantically complete chunks
"""
import json
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
import anthropic

from .config import Config
from .document_processor import DocumentSection, ParsedDocument
from .utils import get_token_count, retry_with_backoff, CostTracker


logger = logging.getLogger(__name__)


@dataclass
class Proposition:
    """Represents an atomic proposition extracted from text"""
    text: str
    section_number: Optional[int]
    section_title: str
    subsection: Optional[str]
    index: int  # Index within section


@dataclass
class SemanticChunk:
    """Represents a semantically complete chunk formed from propositions"""
    chunk_id: str
    text: str
    topic: str
    propositions_used: List[int]  # Indices of propositions
    section_number: Optional[int]
    section_title: str
    subsection: Optional[str]
    token_count: int
    metadata: Dict[str, Any]

    def __post_init__(self):
        if self.token_count == 0:
            self.token_count = get_token_count(self.text)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return asdict(self)


class PropositionalChunker:
    """LLM-based propositional chunking system"""

    def __init__(self, cost_tracker: Optional[CostTracker] = None):
        """
        Initialize propositional chunker

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
    async def extract_propositions(self, section: DocumentSection) -> List[Proposition]:
        """
        Stage 1: Extract atomic propositions from a document section

        Args:
            section: Document section to extract propositions from

        Returns:
            List of atomic propositions
        """
        logger.info(
            f"Extracting propositions from section: {section.section_title} "
            f"({section.token_count} tokens)"
        )

        prompt = f"""<document_section>
{section.content}
</document_section>

Extract all atomic propositions (discrete factual statements) from this section. Each proposition should:
- Be a complete, standalone factual statement
- Contain one clear concept or instruction
- Be understandable without additional context

Return as JSON array of strings:
["proposition 1", "proposition 2", ...]"""

        try:
            message = self.client.messages.create(
                model=Config.PROPOSITION_EXTRACTION_MODEL,
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}]
            )

            # Track cost
            input_tokens = message.usage.input_tokens
            output_tokens = message.usage.output_tokens
            cost = self._calculate_cost(input_tokens, output_tokens, cached_tokens=0)
            self.cost_tracker.add_cost("proposition_extraction", cost)

            logger.info(
                f"Proposition extraction: {input_tokens} input + {output_tokens} output tokens "
                f"(${cost:.4f})"
            )

            # Parse response
            response_text = message.content[0].text.strip()

            # Try to extract JSON from response
            json_match = response_text
            if "```json" in response_text:
                json_match = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                json_match = response_text.split("```")[1].split("```")[0].strip()
            else:
                # Try to find JSON array in the response (look for opening bracket)
                start_idx = response_text.find("[")
                if start_idx != -1:
                    json_match = response_text[start_idx:]

            propositions_text = json.loads(json_match)

            # Convert to Proposition objects
            propositions = [
                Proposition(
                    text=prop,
                    section_number=section.section_number,
                    section_title=section.section_title,
                    subsection=section.subsection,
                    index=i
                )
                for i, prop in enumerate(propositions_text)
            ]

            logger.info(f"Extracted {len(propositions)} propositions")
            return propositions

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from proposition extraction: {e}")
            logger.error(f"Response: {response_text}")
            raise
        except Exception as e:
            logger.error(f"Error extracting propositions: {e}")
            raise

    @retry_with_backoff(
        max_retries=Config.MAX_RETRIES,
        initial_delay=Config.RETRY_DELAY,
        backoff_factor=Config.BACKOFF_FACTOR
    )
    async def group_propositions(
        self,
        propositions: List[Proposition],
        section: DocumentSection,
        start_index: int = 0
    ) -> List[SemanticChunk]:
        """
        Stage 2: Group propositions into semantically complete chunks

        Args:
            propositions: List of propositions to group
            section: Original document section (for context)

        Returns:
            List of semantic chunks
        """
        logger.info(f"Grouping {len(propositions)} propositions into semantic chunks")

        # Format propositions for prompt
        prop_list = "\n".join([f"{i}. {p.text}" for i, p in enumerate(propositions)])

        prompt = f"""<propositions>
{prop_list}
</propositions>

Group these propositions into semantically complete chunks. Each chunk should:
- Contain related propositions that form a complete concept
- Be {Config.MIN_CHUNK_TOKENS}-{Config.MAX_CHUNK_TOKENS} tokens in length
- Be coherent and understandable on its own
- Cover one main topic (e.g., a specific program template, principle, or training concept)

Return as JSON:
[
  {{
    "chunk_text": "combined propositions forming complete concept",
    "topic": "brief description of what this chunk covers",
    "propositions_used": [0, 1, 2]
  }}
]"""

        try:
            message = self.client.messages.create(
                model=Config.PROPOSITION_GROUPING_MODEL,
                max_tokens=8000,
                messages=[{"role": "user", "content": prompt}]
            )

            # Track cost
            input_tokens = message.usage.input_tokens
            output_tokens = message.usage.output_tokens
            cost = self._calculate_cost(input_tokens, output_tokens, cached_tokens=0)
            self.cost_tracker.add_cost("proposition_grouping", cost)

            logger.info(
                f"Proposition grouping: {input_tokens} input + {output_tokens} output tokens "
                f"(${cost:.4f})"
            )

            # Parse response
            response_text = message.content[0].text.strip()

            # Try to extract JSON from response
            json_match = response_text
            if "```json" in response_text:
                json_match = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                json_match = response_text.split("```")[1].split("```")[0].strip()
            else:
                # Try to find JSON array in the response (look for opening bracket)
                start_idx = response_text.find("[")
                if start_idx != -1:
                    json_match = response_text[start_idx:]

            grouped_chunks = json.loads(json_match)

            # Convert to SemanticChunk objects
            chunks = []
            for i, chunk_data in enumerate(grouped_chunks):
                chunk_id = f"chunk_{start_index + i}"  # Global unique ID

                chunk = SemanticChunk(
                    chunk_id=chunk_id,
                    text=chunk_data["chunk_text"],
                    topic=chunk_data["topic"],
                    propositions_used=chunk_data["propositions_used"],
                    section_number=section.section_number,
                    section_title=section.section_title,
                    subsection=section.subsection,
                    token_count=0,  # Will be calculated in __post_init__
                    metadata=section.metadata.copy()
                )
                chunks.append(chunk)

            logger.info(f"Created {len(chunks)} semantic chunks")

            # Log chunk sizes
            for chunk in chunks:
                logger.debug(
                    f"Chunk {chunk.chunk_id}: {chunk.token_count} tokens - {chunk.topic}"
                )

            return chunks

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from proposition grouping: {e}")
            logger.error(f"Response: {response_text}")
            raise
        except Exception as e:
            logger.error(f"Error grouping propositions: {e}")
            raise

    async def chunk_document(self, document: ParsedDocument) -> List[SemanticChunk]:
        """
        Perform full propositional chunking on a document

        Args:
            document: Parsed document to chunk

        Returns:
            List of semantic chunks
        """
        logger.info(f"Starting propositional chunking for: {document.title}")
        logger.info(f"Processing {document.num_sections} sections")

        all_chunks = []
        global_chunk_counter = 0  # Global counter for unique chunk IDs

        for i, section in enumerate(document.sections, 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"Processing section {i}/{document.num_sections}: {section.section_title}")
            logger.info(f"{'='*60}")

            try:
                # Stage 1: Extract propositions
                propositions = await self.extract_propositions(section)

                if not propositions:
                    logger.warning(f"No propositions extracted from section: {section.section_title}")
                    continue

                # Stage 2: Group propositions
                chunks = await self.group_propositions(propositions, section, global_chunk_counter)

                # Update global counter
                global_chunk_counter += len(chunks)

                all_chunks.extend(chunks)

            except Exception as e:
                logger.error(
                    f"Error processing section '{section.section_title}': {e}",
                    exc_info=True
                )
                # Continue with next section rather than failing completely
                continue

        logger.info(f"\n{'='*60}")
        logger.info(f"Propositional Chunking Complete")
        logger.info(f"{'='*60}")
        logger.info(f"Total chunks created: {len(all_chunks)}")

        if len(all_chunks) > 0:
            logger.info(f"Average chunk size: {sum(c.token_count for c in all_chunks) / len(all_chunks):.0f} tokens")
            logger.info(f"Min chunk size: {min(c.token_count for c in all_chunks)} tokens")
            logger.info(f"Max chunk size: {max(c.token_count for c in all_chunks)} tokens")
        else:
            logger.error("No chunks were created. Check API keys and credits.")

        return all_chunks

    @staticmethod
    def _calculate_cost(input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> float:
        """Calculate cost for Claude API call"""
        # Claude 3.5 Haiku pricing
        input_cost = input_tokens * (1.00 / 1_000_000)
        output_cost = output_tokens * (5.00 / 1_000_000)
        cached_cost = cached_tokens * (0.10 / 1_000_000)

        return input_cost + output_cost + cached_cost
