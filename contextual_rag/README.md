# Contextual RAG System for NowvaLiveKit

A production-ready Retrieval-Augmented Generation (RAG) system built specifically for the NowvaLiveKit fitness coaching platform.

## Overview

This system replaces the static CAG (Cache-Augmented Generation) approach with dynamic retrieval using:

- **Propositional Chunking**: LLM-based intelligent chunking for semantically complete chunks
- **Anthropic's Contextual Retrieval**: Reduces retrieval failures by 67% (exact prompt from Anthropic research)
- **Hybrid Search**: Combines semantic search (Voyage-3 embeddings + ChromaDB) with BM25 lexical search using Reciprocal Rank Fusion (RRF)
- **Cohere Reranking**: Final reranking with rerank-v3.5 for maximum precision

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        INGESTION PIPELINE                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Parse CAG Document → Sections                               │
│  2. Extract Propositions (Claude Haiku)                         │
│  3. Group into Semantic Chunks (Claude Haiku)                   │
│  4. Apply Contextual Retrieval (Claude Haiku + caching)         │
│  5. Generate Embeddings (Voyage-3)                              │
│  6. Store in ChromaDB + BM25 Index                              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                       RETRIEVAL PIPELINE                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Query → Embed (Voyage-3)                                       │
│     ↓                                                            │
│  Hybrid Search (Semantic + BM25 with RRF) → Top 20             │
│     ↓                                                            │
│  Rerank (Cohere rerank-v3.5) → Top 10                          │
│     ↓                                                            │
│  Format for LLM → Return Context                                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Installation

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Up API Keys

Add to `.env`:

```bash
# Existing keys
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# New for RAG
VOYAGE_API_KEY=pa-...
COHERE_API_KEY=...
```

Get your API keys:
- **Anthropic**: https://console.anthropic.com/
- **Voyage AI**: https://www.voyageai.com/
- **Cohere**: https://dashboard.cohere.com/

### 3. Run Ingestion

Process your CAG knowledge base:

```bash
python -m contextual_rag.ingestion_pipeline \
  --input src/knowledge/cag_periodization.txt \
  --rebuild
```

This will:
- Parse the document
- Extract and group propositions
- Apply contextual retrieval
- Generate embeddings
- Store in ChromaDB and BM25 index

**Expected time**: ~5-10 minutes for the full CAG file

**Expected cost**: ~$0.06 (one-time ingestion cost)

## Usage

### Basic Query

```python
from contextual_rag import retrieve_for_program_generation

# Retrieve relevant knowledge
context = await retrieve_for_program_generation(
    query="intermediate hypertrophy 4 days per week",
    top_k=10,
    use_reranker=True,
    max_tokens=2000
)

# Use context in your LLM prompt
prompt = f"""
{base_system_prompt}

{context}

# User Request
Generate a 12-week program for intermediate hypertrophy...
"""
```

### Integration with Program Generator

The system is designed to integrate seamlessly with `program_generator_v2.py`:

```python
from contextual_rag.query_interface import retrieve_for_program_generation

async def generate_program_with_rag(params):
    # Build query from parameters
    query = f"{params['fitness_level']} {params['goal_category']} "
    query += f"{params['days_per_week']} days per week"

    # Retrieve relevant knowledge
    rag_context = await retrieve_for_program_generation(
        query=query,
        top_k=10,
        use_reranker=True
    )

    # Build system prompt with RAG context
    system_prompt = f"{base_prompt}\n\n{rag_context}\n\n{instructions}"

    # Generate program with OpenAI
    response = await client.beta.chat.completions.parse(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        response_format=ProgramBatchSchema
    )
```

### Advanced Usage

Get raw chunks (for testing/debugging):

```python
from contextual_rag.query_interface import retrieve_chunks

chunks = await retrieve_chunks(
    query="novice strength program 3 days",
    top_k=5,
    use_reranker=True
)

for chunk in chunks:
    print(f"Score: {chunk.score:.4f}")
    print(f"Topic: {chunk.metadata['topic']}")
    print(f"Text: {chunk.text[:200]}...")
    print()
```

Get system statistics:

```python
from contextual_rag.query_interface import get_rag_stats

stats = get_rag_stats()
print(stats)
# Output:
# {
#   "vector_store": {"total_chunks": 35, ...},
#   "bm25_index": {"vocabulary_size": 1247, ...},
#   "cost_tracker": {"total": 0.064, ...}
# }
```

## Cost Analysis

### One-Time Ingestion (for full CAG file)

| Component | Usage | Cost |
|-----------|-------|------|
| Propositional extraction | ~20 sections × 2K tokens | $0.02 |
| Proposition grouping | ~200 propositions | $0.01 |
| Contextual retrieval | ~35 chunks (90% cached) | $0.02 |
| Voyage-3 embeddings | ~35 chunks × 500 tokens | $0.01 |
| **Total** | | **$0.06** |

### Per-Generation Recurring Costs

**CAG (Old Approach)**:
- Input: 20,000 tokens (10,000 cached)
- Output: 4,000 tokens
- Cost: ~$0.066

**RAG (New Approach)**:
- Voyage-3 query embedding: $0.000006
- Cohere reranking: $0.002
- OpenAI (1,500 input + 4,000 output): $0.044
- **Total: ~$0.046**

**Savings: 30% per generation** ($0.020 saved per program)

### Scalability

As knowledge base grows:
- **CAG**: Cost increases linearly with KB size
- **RAG**: Cost stays constant (always retrieve top 10)

At 2× knowledge base:
- CAG: ~$0.090 per generation
- RAG: ~$0.046 per generation (unchanged)
- **Savings: 49%**

## Testing

Run the test script (after ingestion):

```bash
# Test retrieval quality
python -c "
import asyncio
from contextual_rag.query_interface import retrieve_for_program_generation

async def test():
    queries = [
        'novice strength program 3 days per week',
        'intermediate hypertrophy 4 day upper lower',
        'advanced powerlifting peaking 12 weeks'
    ]

    for query in queries:
        print(f'\nQuery: {query}')
        print('='*60)
        context = await retrieve_for_program_generation(query, top_k=3)
        print(context[:500] + '...')

asyncio.run(test())
"
```

## Modules

- **[config.py](config.py)**: Configuration and API keys
- **[document_processor.py](document_processor.py)**: Parse CAG into sections
- **[propositional_chunker.py](propositional_chunker.py)**: LLM-based intelligent chunking
- **[contextual_enricher.py](contextual_enricher.py)**: Anthropic's contextual retrieval
- **[embeddings.py](embeddings.py)**: Voyage AI embedding generation
- **[vector_store.py](vector_store.py)**: ChromaDB operations
- **[bm25_index.py](bm25_index.py)**: BM25 lexical search
- **[hybrid_retriever.py](hybrid_retriever.py)**: Semantic + BM25 fusion (RRF)
- **[reranker.py](reranker.py)**: Cohere reranking
- **[query_interface.py](query_interface.py)**: Main API
- **[ingestion_pipeline.py](ingestion_pipeline.py)**: Orchestration
- **[utils.py](utils.py)**: Utilities

## Next Steps

1. **Run ingestion** on your CAG file
2. **Test retrieval** with sample queries
3. **Integrate with program generator** (see plan file for details)
4. **A/B test** RAG vs CAG (10% → 50% → 100% rollout)
5. **Monitor costs** and retrieval quality

## Troubleshooting

### "BM25 index not found"
Run ingestion first:
```bash
python -m contextual_rag.ingestion_pipeline --input src/knowledge/cag_periodization.txt
```

### "Missing required API keys"
Add all three API keys to `.env`:
```bash
ANTHROPIC_API_KEY=sk-ant-...
VOYAGE_API_KEY=pa-...
COHERE_API_KEY=...
```

### ChromaDB errors
Delete and rebuild:
```bash
rm -rf contextual_rag/data/chroma_db
python -m contextual_rag.ingestion_pipeline --input src/knowledge/cag_periodization.txt --rebuild
```

## References

- **Anthropic Contextual Retrieval**: https://www.anthropic.com/news/contextual-retrieval
- **Voyage AI Documentation**: https://docs.voyageai.com/
- **Cohere Rerank**: https://docs.cohere.com/docs/reranking
- **ChromaDB**: https://docs.trychroma.com/
