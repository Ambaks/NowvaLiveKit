"""
Utility functions for the RAG system
"""
import logging
import time
import tiktoken
from typing import List, Dict, Any, Optional
from functools import wraps


# Initialize logger
logger = logging.getLogger(__name__)


def get_token_count(text: str, model: str = "gpt-4o") -> int:
    """
    Count tokens in text using tiktoken

    Args:
        text: Text to count tokens for
        model: Model name for tokenizer (default: gpt-4o)

    Returns:
        Number of tokens
    """
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        # Fallback to cl100k_base (used by GPT-4, GPT-3.5-turbo)
        encoding = tiktoken.get_encoding("cl100k_base")

    return len(encoding.encode(text))


def truncate_text_to_tokens(text: str, max_tokens: int, model: str = "gpt-4o") -> str:
    """
    Truncate text to fit within max token limit

    Args:
        text: Text to truncate
        max_tokens: Maximum number of tokens
        model: Model name for tokenizer

    Returns:
        Truncated text
    """
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")

    tokens = encoding.encode(text)
    if len(tokens) <= max_tokens:
        return text

    truncated_tokens = tokens[:max_tokens]
    return encoding.decode(truncated_tokens)


def retry_with_backoff(max_retries: int = 3, initial_delay: float = 1.0, backoff_factor: float = 2.0):
    """
    Decorator for retrying functions with exponential backoff

    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        backoff_factor: Multiplier for delay after each retry
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt == max_retries:
                        logger.error(f"{func.__name__} failed after {max_retries} retries: {e}")
                        raise

                    logger.warning(
                        f"{func.__name__} attempt {attempt + 1}/{max_retries + 1} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    delay *= backoff_factor

            raise last_exception

        return wrapper
    return decorator


class CostTracker:
    """Track API costs for RAG operations"""

    def __init__(self):
        self.costs: Dict[str, float] = {
            "contextualization": 0.0,
            "proposition_extraction": 0.0,
            "proposition_grouping": 0.0,
            "embeddings": 0.0,
            "reranking": 0.0,
            "total": 0.0,
        }
        self.operations: Dict[str, int] = {
            "contextualization": 0,
            "proposition_extraction": 0,
            "proposition_grouping": 0,
            "embeddings": 0,
            "reranking": 0,
        }

    def add_cost(self, operation: str, cost: float) -> None:
        """Add cost for an operation"""
        if operation in self.costs:
            self.costs[operation] += cost
            self.costs["total"] += cost
            self.operations[operation] += 1

    def log_summary(self) -> None:
        """Log cost summary"""
        logger.info("=" * 60)
        logger.info("RAG Cost Summary")
        logger.info("=" * 60)
        for op, cost in self.costs.items():
            if op != "total":
                count = self.operations.get(op, 0)
                logger.info(f"{op:25s}: ${cost:.4f} ({count} operations)")
        logger.info("-" * 60)
        logger.info(f"{'TOTAL':25s}: ${self.costs['total']:.4f}")
        logger.info("=" * 60)

    def get_summary(self) -> Dict[str, Any]:
        """Get cost summary as dictionary"""
        return {
            "costs": self.costs.copy(),
            "operations": self.operations.copy(),
        }


def format_chunks_for_llm(chunks: List[Dict[str, Any]], max_tokens: Optional[int] = None) -> str:
    """
    Format retrieved chunks for LLM consumption

    Args:
        chunks: List of chunk dictionaries with 'text', 'topic', 'section' keys
        max_tokens: Optional max token limit

    Returns:
        Formatted string ready to inject into LLM prompt
    """
    formatted = "# Retrieved Training Knowledge\n\n"

    for i, chunk in enumerate(chunks, 1):
        section = chunk.get("section_title", "Unknown Section")
        topic = chunk.get("topic", "")
        text = chunk.get("text", "")

        chunk_header = f"## Source {i}"
        if topic:
            chunk_header += f": {topic}"
        chunk_header += f" (from {section})"

        formatted += f"{chunk_header}\n\n{text}\n\n"

    if max_tokens:
        formatted = truncate_text_to_tokens(formatted, max_tokens)

    return formatted


def setup_logging(level: str = "INFO") -> None:
    """Setup logging configuration for RAG system"""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
