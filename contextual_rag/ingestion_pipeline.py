"""
Ingestion Pipeline - Orchestrate Full RAG Creation

Complete pipeline from CAG document to searchable RAG system:
1. Parse document into sections
2. Extract propositions and group into semantic chunks
3. Apply Anthropic's contextual retrieval
4. Generate embeddings
5. Store in ChromaDB and BM25 index
"""
import logging
import json
import time
import pickle
from pathlib import Path
from typing import Optional
import asyncio

from .config import Config
from .document_processor import DocumentProcessor
from .propositional_chunker import PropositionalChunker
from .contextual_enricher import ContextualEnricher
from .embeddings import EmbeddingGenerator
from .vector_store import VectorStore
from .bm25_index import BM25Index
from .utils import CostTracker, setup_logging


logger = logging.getLogger(__name__)


class IngestionPipeline:
    """Orchestrate full RAG ingestion pipeline"""

    def __init__(self):
        """Initialize ingestion pipeline"""
        setup_logging(Config.LOG_LEVEL)

        self.cost_tracker = CostTracker()

        # Initialize components
        self.propositional_chunker = PropositionalChunker(cost_tracker=self.cost_tracker)
        self.contextual_enricher = ContextualEnricher(cost_tracker=self.cost_tracker)
        self.embedding_generator = EmbeddingGenerator(cost_tracker=self.cost_tracker)
        self.vector_store = VectorStore()
        self.bm25_index = BM25Index()

    def _save_checkpoint(self, enriched_chunks, document):
        """Save enriched chunks to checkpoint file"""
        checkpoint_data = {
            "enriched_chunks": enriched_chunks,
            "document": document,
            "timestamp": time.time()
        }
        with open(Config.CHECKPOINT_PATH, 'wb') as f:
            pickle.dump(checkpoint_data, f)
        logger.info(f"Saved checkpoint with {len(enriched_chunks)} enriched chunks")

    def _load_checkpoint(self):
        """Load enriched chunks from checkpoint file"""
        if not Config.CHECKPOINT_PATH.exists():
            return None

        try:
            with open(Config.CHECKPOINT_PATH, 'rb') as f:
                checkpoint_data = pickle.load(f)
            logger.info(f"Loaded checkpoint with {len(checkpoint_data['enriched_chunks'])} enriched chunks")
            return checkpoint_data
        except Exception as e:
            logger.warning(f"Failed to load checkpoint: {e}")
            return None

    def _delete_checkpoint(self):
        """Delete checkpoint file"""
        if Config.CHECKPOINT_PATH.exists():
            Config.CHECKPOINT_PATH.unlink()
            logger.info("Deleted checkpoint file")

    async def ingest_document(
        self,
        filepath: str,
        rebuild: bool = False
    ) -> dict:
        """
        Complete ingestion pipeline for a single document

        Args:
            filepath: Path to document to ingest
            rebuild: If True, delete existing data and rebuild from scratch

        Returns:
            Ingestion statistics
        """
        start_time = time.time()

        logger.info("="*80)
        logger.info("CONTEXTUAL RAG INGESTION PIPELINE")
        logger.info("="*80)
        logger.info(f"Document: {filepath}")
        logger.info(f"Rebuild: {rebuild}")
        logger.info("="*80)

        # Validate API keys
        try:
            Config.validate()
            Config.ensure_directories()
        except ValueError as e:
            logger.error(f"Configuration error: {e}")
            raise

        # Check for checkpoint (unless rebuild=True)
        checkpoint = None
        if not rebuild:
            checkpoint = self._load_checkpoint()

        if checkpoint:
            logger.info("="*80)
            logger.info("RESUMING FROM CHECKPOINT")
            logger.info("="*80)
            logger.info("Skipping Steps 1-3 (already completed)")
            enriched_chunks = checkpoint["enriched_chunks"]
            document = checkpoint["document"]
        else:
            # Delete old checkpoint if rebuild=True
            if rebuild:
                self._delete_checkpoint()

            # Step 1: Parse document
            logger.info("\n" + "="*80)
            logger.info("STEP 1: PARSING DOCUMENT")
            logger.info("="*80)

            document = DocumentProcessor.parse_cag_file(filepath)

            logger.info(f"Parsed {document.num_sections} sections")
            logger.info(f"Total tokens: {document.total_tokens:,}")

            # Step 2: Propositional chunking
            logger.info("\n" + "="*80)
            logger.info("STEP 2: PROPOSITIONAL CHUNKING")
            logger.info("="*80)

            semantic_chunks = await self.propositional_chunker.chunk_document(document)

            logger.info(f"Created {len(semantic_chunks)} semantic chunks")

            # Validate chunks were created
            if len(semantic_chunks) == 0:
                logger.error("="*80)
                logger.error("INGESTION FAILED: No chunks were created")
                logger.error("="*80)
                logger.error("Possible causes:")
                logger.error("1. Anthropic API key is missing or invalid")
                logger.error("2. Anthropic account has insufficient credits")
                logger.error("3. API rate limits exceeded")
                logger.error("")
                logger.error("Please check your ANTHROPIC_API_KEY and account credits at:")
                logger.error("https://console.anthropic.com/settings/plans")
                raise RuntimeError("Ingestion failed: No chunks were created. Check API key and credits.")

            # Step 3: Contextual enrichment
            logger.info("\n" + "="*80)
            logger.info("STEP 3: CONTEXTUAL ENRICHMENT (ANTHROPIC)")
            logger.info("="*80)

            enriched_chunks = await self.contextual_enricher.enrich_chunks(
                chunks=semantic_chunks,
                document=document
            )

            logger.info(f"Enriched {len(enriched_chunks)} chunks with contextual descriptions")

            # Save checkpoint after Step 3
            self._save_checkpoint(enriched_chunks, document)

        # Step 4: Generate embeddings
        logger.info("\n" + "="*80)
        logger.info("STEP 4: EMBEDDING GENERATION (VOYAGE AI)")
        logger.info("="*80)

        embeddings = await self.embedding_generator.embed_enriched_chunks(enriched_chunks)

        logger.info(f"Generated {len(embeddings)} embeddings")

        # Step 5: Store in ChromaDB
        logger.info("\n" + "="*80)
        logger.info("STEP 5: CHROMADB STORAGE")
        logger.info("="*80)

        self.vector_store.create_or_get_collection(reset=rebuild)
        self.vector_store.add_chunks(enriched_chunks, embeddings)

        logger.info(f"Stored {len(enriched_chunks)} chunks in ChromaDB")

        # Step 6: Build BM25 index
        logger.info("\n" + "="*80)
        logger.info("STEP 6: BM25 INDEX CREATION")
        logger.info("="*80)

        self.bm25_index.build_index(enriched_chunks)
        self.bm25_index.save()

        logger.info(f"Built and saved BM25 index")

        # Step 7: Save metadata
        logger.info("\n" + "="*80)
        logger.info("STEP 7: SAVING METADATA")
        logger.info("="*80)

        self._save_metadata(enriched_chunks, document)

        # Final statistics
        elapsed_time = time.time() - start_time

        logger.info("\n" + "="*80)
        logger.info("INGESTION COMPLETE")
        logger.info("="*80)
        logger.info(f"Document: {document.title}")
        logger.info(f"Chunks created: {len(enriched_chunks)}")
        logger.info(f"Time elapsed: {elapsed_time/60:.2f} minutes")
        logger.info("="*80)

        # Cost summary
        self.cost_tracker.log_summary()

        # Delete checkpoint after successful completion
        self._delete_checkpoint()

        stats = {
            "document_title": document.title,
            "document_filepath": filepath,
            "document_tokens": document.total_tokens,
            "sections_parsed": document.num_sections,
            "chunks_created": len(enriched_chunks),
            "chunks_enriched": len(enriched_chunks),
            "embeddings_generated": len(embeddings),
            "time_elapsed_minutes": elapsed_time / 60,
            "costs": self.cost_tracker.get_summary(),
        }

        return stats

    def _save_metadata(self, enriched_chunks, document):
        """Save chunk metadata to JSON file"""
        metadata = {
            "document_title": document.title,
            "document_filepath": document.filepath,
            "total_chunks": len(enriched_chunks),
            "chunks": [chunk.to_dict() for chunk in enriched_chunks]
        }

        with open(Config.CHUNKS_METADATA_PATH, 'w') as f:
            json.dump(metadata, f, indent=2)

        logger.info(f"Saved metadata to: {Config.CHUNKS_METADATA_PATH}")


async def main():
    """CLI entry point for ingestion pipeline"""
    import argparse

    parser = argparse.ArgumentParser(description="Ingest documents into RAG system")
    parser.add_argument(
        "--input",
        type=str,
        required=True,
        help="Path to CAG document to ingest"
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Rebuild from scratch (delete existing data)"
    )

    args = parser.parse_args()

    pipeline = IngestionPipeline()
    stats = await pipeline.ingest_document(
        filepath=args.input,
        rebuild=args.rebuild
    )

    print("\n" + "="*80)
    print("INGESTION STATISTICS")
    print("="*80)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
