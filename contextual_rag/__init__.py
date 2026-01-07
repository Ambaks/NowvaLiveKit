"""
Contextual RAG System for NowvaLiveKit Fitness Platform

A production-ready RAG system using:
- Propositional chunking for semantically complete chunks
- Anthropic's contextual retrieval (67% reduction in retrieval failures)
- Hybrid search (Voyage-3 semantic + BM25 lexical)
- Cohere reranking for precision
"""

__version__ = "1.0.0"

from .config import Config
from .query_interface import retrieve_for_program_generation

__all__ = [
    "Config",
    "retrieve_for_program_generation",
]
