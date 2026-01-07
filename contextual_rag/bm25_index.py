"""
BM25 Index - Lexical Search

Implements BM25Okapi for keyword-based search, complementing semantic search.
"""
import logging
import pickle
import re
from typing import List, Tuple, Optional
from pathlib import Path
from rank_bm25 import BM25Okapi

from .config import Config
from .contextual_enricher import EnrichedChunk


logger = logging.getLogger(__name__)


class BM25Index:
    """BM25 index for lexical keyword search"""

    def __init__(self):
        """Initialize BM25 index"""
        self.index: Optional[BM25Okapi] = None
        self.chunk_ids: List[str] = []
        self.chunk_texts: List[str] = []
        self.tokenized_corpus: List[List[str]] = []

    @staticmethod
    def tokenize(text: str) -> List[str]:
        """
        Tokenize text for BM25

        Args:
            text: Text to tokenize

        Returns:
            List of tokens
        """
        # Lowercase
        text = text.lower()

        # Remove punctuation except hyphens (for compound-words)
        text = re.sub(r'[^\w\s-]', ' ', text)

        # Split on whitespace
        tokens = text.split()

        # Remove very short tokens (< 2 chars) and very long (> 20)
        tokens = [t for t in tokens if 2 <= len(t) <= 20]

        return tokens

    def build_index(self, enriched_chunks: List[EnrichedChunk]) -> None:
        """
        Build BM25 index from enriched chunks

        Args:
            enriched_chunks: List of enriched chunks to index
        """
        logger.info(f"Building BM25 index from {len(enriched_chunks)} chunks")

        # Store chunk IDs and texts
        self.chunk_ids = [chunk.chunk_id for chunk in enriched_chunks]
        self.chunk_texts = [chunk.full_text for chunk in enriched_chunks]

        # Tokenize corpus
        self.tokenized_corpus = [
            self.tokenize(chunk.full_text)
            for chunk in enriched_chunks
        ]

        # Build BM25 index
        self.index = BM25Okapi(self.tokenized_corpus)

        logger.info(f"BM25 index built with {len(self.chunk_ids)} documents")

        # Log vocabulary size
        vocab = set()
        for tokens in self.tokenized_corpus:
            vocab.update(tokens)
        logger.info(f"Vocabulary size: {len(vocab)} unique tokens")

    def search(self, query: str, top_k: int = 20) -> List[Tuple[str, float, str]]:
        """
        Search BM25 index for relevant chunks

        Args:
            query: Search query
            top_k: Number of results to return

        Returns:
            List of tuples: (chunk_id, score, text)
        """
        if self.index is None:
            raise ValueError("Index not built. Call build_index() first.")

        logger.debug(f"BM25 search: {query[:100]}... (top_k={top_k})")

        # Tokenize query
        tokenized_query = self.tokenize(query)

        # Get scores for all documents
        scores = self.index.get_scores(tokenized_query)

        # Get top-k indices
        top_indices = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True
        )[:top_k]

        # Build results
        results = [
            (
                self.chunk_ids[i],
                float(scores[i]),
                self.chunk_texts[i]
            )
            for i in top_indices
        ]

        logger.debug(f"BM25 returned {len(results)} results")
        if results:
            logger.debug(f"Top BM25 score: {results[0][1]:.4f}")

        return results

    def save(self, filepath: Optional[Path] = None) -> None:
        """
        Save BM25 index to disk

        Args:
            filepath: Path to save index (defaults to Config.BM25_INDEX_PATH)
        """
        if self.index is None:
            raise ValueError("No index to save. Build index first.")

        filepath = filepath or Config.BM25_INDEX_PATH
        filepath.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Saving BM25 index to: {filepath}")

        # Save all index components
        index_data = {
            "index": self.index,
            "chunk_ids": self.chunk_ids,
            "chunk_texts": self.chunk_texts,
            "tokenized_corpus": self.tokenized_corpus
        }

        with open(filepath, 'wb') as f:
            pickle.dump(index_data, f, protocol=pickle.HIGHEST_PROTOCOL)

        file_size_mb = filepath.stat().st_size / (1024 * 1024)
        logger.info(f"BM25 index saved ({file_size_mb:.2f} MB)")

    def load(self, filepath: Optional[Path] = None) -> None:
        """
        Load BM25 index from disk

        Args:
            filepath: Path to load index from (defaults to Config.BM25_INDEX_PATH)
        """
        filepath = filepath or Config.BM25_INDEX_PATH

        if not filepath.exists():
            raise FileNotFoundError(f"BM25 index not found at: {filepath}")

        logger.info(f"Loading BM25 index from: {filepath}")

        with open(filepath, 'rb') as f:
            index_data = pickle.load(f)

        self.index = index_data["index"]
        self.chunk_ids = index_data["chunk_ids"]
        self.chunk_texts = index_data["chunk_texts"]
        self.tokenized_corpus = index_data["tokenized_corpus"]

        logger.info(f"BM25 index loaded ({len(self.chunk_ids)} documents)")

    def get_stats(self) -> dict:
        """Get statistics about the BM25 index"""
        if self.index is None:
            return {"status": "not_built"}

        vocab = set()
        for tokens in self.tokenized_corpus:
            vocab.update(tokens)

        return {
            "status": "ready",
            "total_documents": len(self.chunk_ids),
            "vocabulary_size": len(vocab),
            "avg_doc_length": sum(len(tokens) for tokens in self.tokenized_corpus) / len(self.tokenized_corpus),
            "storage_path": str(Config.BM25_INDEX_PATH),
        }
