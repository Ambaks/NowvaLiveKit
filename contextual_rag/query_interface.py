"""
Query Interface - Main API for Program Generator

Provides simple, high-level interface for retrieving relevant fitness knowledge.
"""
import logging
from typing import Dict, Any, Optional, List

from .config import Config
from .vector_store import VectorStore
from .bm25_index import BM25Index
from .embeddings import EmbeddingGenerator
from .hybrid_retriever import HybridRetriever, RetrievedChunk
from .reranker import Reranker
from .utils import CostTracker, format_chunks_for_llm, get_token_count


logger = logging.getLogger(__name__)


# Global instances (initialized once)
_vector_store: Optional[VectorStore] = None
_bm25_index: Optional[BM25Index] = None
_embedding_generator: Optional[EmbeddingGenerator] = None
_hybrid_retriever: Optional[HybridRetriever] = None
_reranker: Optional[Reranker] = None
_cost_tracker: Optional[CostTracker] = None


def _initialize_rag_system():
    """Initialize RAG system components (lazy initialization)"""
    global _vector_store, _bm25_index, _embedding_generator, _hybrid_retriever, _reranker, _cost_tracker

    if _vector_store is not None:
        return  # Already initialized

    logger.info("Initializing RAG system...")

    # Initialize cost tracker
    _cost_tracker = CostTracker()

    # Initialize vector store
    _vector_store = VectorStore()
    _vector_store.create_or_get_collection(reset=False)

    # Initialize BM25 index
    _bm25_index = BM25Index()
    try:
        _bm25_index.load()
    except FileNotFoundError:
        logger.error(
            f"BM25 index not found at {Config.BM25_INDEX_PATH}. "
            f"Please run ingestion pipeline first."
        )
        raise

    # Initialize embedding generator
    _embedding_generator = EmbeddingGenerator(cost_tracker=_cost_tracker)

    # Initialize hybrid retriever
    _hybrid_retriever = HybridRetriever(
        vector_store=_vector_store,
        bm25_index=_bm25_index,
        embedding_generator=_embedding_generator,
        cost_tracker=_cost_tracker
    )

    # Initialize reranker
    _reranker = Reranker(cost_tracker=_cost_tracker)

    logger.info("RAG system initialized successfully")
    logger.info(f"Vector store: {_vector_store.get_stats()}")
    logger.info(f"BM25 index: {_bm25_index.get_stats()}")


async def retrieve_for_program_generation(
    query: str,
    top_k: int = Config.FINAL_CHUNKS_MAX,
    use_reranker: bool = True,
    max_tokens: Optional[int] = Config.MAX_TOKENS_BUDGET,
    metadata_filter: Optional[Dict[str, Any]] = None
) -> str:
    """
    Retrieve relevant fitness knowledge for program generation

    This is the main API used by the program generator.

    Args:
        query: Search query (e.g., "intermediate hypertrophy 4 days per week")
        top_k: Maximum number of chunks to return
        use_reranker: Whether to use Cohere reranking (default: True)
        max_tokens: Maximum token budget for returned context
        metadata_filter: Optional metadata filter

    Returns:
        Formatted string with retrieved knowledge, ready for LLM prompt
    """
    # Initialize system if needed
    _initialize_rag_system()

    logger.info(f"Retrieving knowledge for query: {query}")
    logger.info(f"Parameters: top_k={top_k}, use_reranker={use_reranker}, max_tokens={max_tokens}")

    # Step 1: Hybrid retrieval (semantic + BM25 with RRF)
    hybrid_results = await _hybrid_retriever.retrieve(
        query=query,
        top_k=20,  # Get more candidates for reranking
        metadata_filter=metadata_filter
    )

    logger.info(f"Hybrid retrieval returned {len(hybrid_results)} chunks")

    # Step 2: Reranking (optional)
    if use_reranker and len(hybrid_results) > 0:
        final_results = await _reranker.rerank(
            query=query,
            chunks=hybrid_results,
            top_n=top_k
        )
        logger.info(f"Reranker returned {len(final_results)} chunks")
    else:
        final_results = hybrid_results[:top_k]
        logger.info(f"Using top {len(final_results)} hybrid results (no reranking)")

    # Step 3: Token budget management
    selected_chunks = _select_chunks_within_budget(
        final_results,
        max_tokens=max_tokens
    )

    logger.info(f"Selected {len(selected_chunks)} chunks within token budget")

    # Step 4: Format for LLM
    formatted_context = _format_for_program_generator(selected_chunks)

    tokens = get_token_count(formatted_context)
    logger.info(f"Formatted context: {tokens} tokens")

    # Log cost summary
    _cost_tracker.log_summary()

    return formatted_context


async def retrieve_chunks(
    query: str,
    top_k: int = 10,
    use_reranker: bool = True
) -> List[RetrievedChunk]:
    """
    Retrieve chunks (raw objects, not formatted)

    Useful for testing and debugging.

    Args:
        query: Search query
        top_k: Number of chunks to return
        use_reranker: Whether to use reranking

    Returns:
        List of retrieved chunks
    """
    _initialize_rag_system()

    # Hybrid retrieval
    hybrid_results = await _hybrid_retriever.retrieve(query=query, top_k=20)

    # Rerank if requested
    if use_reranker:
        return await _reranker.rerank(query, hybrid_results, top_n=top_k)
    else:
        return hybrid_results[:top_k]


def _select_chunks_within_budget(
    chunks: List[RetrievedChunk],
    max_tokens: Optional[int]
) -> List[RetrievedChunk]:
    """
    Select chunks that fit within token budget

    Always includes top 3, then adds more until budget exceeded.

    Args:
        chunks: List of chunks to select from
        max_tokens: Maximum token budget (None = no limit)

    Returns:
        Selected chunks
    """
    if max_tokens is None:
        return chunks

    selected = []
    total_tokens = 0

    for i, chunk in enumerate(chunks):
        chunk_tokens = get_token_count(chunk.text)

        # Always include top 3
        if i < Config.FINAL_CHUNKS_MIN:
            selected.append(chunk)
            total_tokens += chunk_tokens
        elif total_tokens + chunk_tokens <= max_tokens:
            selected.append(chunk)
            total_tokens += chunk_tokens
        else:
            break

    logger.debug(f"Selected {len(selected)} chunks ({total_tokens} tokens)")
    return selected


def _format_for_program_generator(chunks: List[RetrievedChunk]) -> str:
    """
    Format chunks for program generator LLM

    Args:
        chunks: List of chunks to format

    Returns:
        Formatted string
    """
    formatted = "# Retrieved Training Knowledge\n\n"

    for i, chunk in enumerate(chunks, 1):
        topic = chunk.metadata.get("topic", "Unknown")
        section = chunk.metadata.get("section_title", "Unknown Section")

        header = f"## Source {i}: {topic}\n"
        header += f"*From: {section}*\n\n"

        formatted += header + chunk.text + "\n\n---\n\n"

    return formatted


def get_rag_stats() -> Dict[str, Any]:
    """Get statistics about the RAG system"""
    try:
        _initialize_rag_system()
        return {
            "vector_store": _vector_store.get_stats(),
            "bm25_index": _bm25_index.get_stats(),
            "cost_tracker": _cost_tracker.get_summary(),
        }
    except Exception as e:
        return {"error": str(e)}
