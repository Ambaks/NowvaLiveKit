"""
Pricing Configuration for All AI Services
Centralized pricing data for cost calculation
Updated: 2025-01-04
"""

# =============================================================================
# OPENAI PRICING
# =============================================================================
OPENAI_PRICING = {
    "gpt-4o": {
        "input": 2.50 / 1_000_000,      # $2.50 per 1M tokens
        "output": 10.00 / 1_000_000,     # $10.00 per 1M tokens
        "cached_input": 1.25 / 1_000_000 # 50% discount
    },
    "gpt-4o-mini": {
        "input": 0.150 / 1_000_000,      # $0.15 per 1M tokens
        "output": 0.600 / 1_000_000,     # $0.60 per 1M tokens
        "cached_input": 0.075 / 1_000_000
    },
    "gpt-4o-realtime-preview": {
        "text_input": 5.00 / 1_000_000,
        "text_output": 20.00 / 1_000_000,
        "audio_input": 100.00 / 1_000_000,   # $100 per 1M tokens
        "audio_output": 200.00 / 1_000_000   # $200 per 1M tokens
    }
}

# =============================================================================
# RAG SYSTEM PRICING
# =============================================================================

# Anthropic Claude (for contextualization)
ANTHROPIC_PRICING = {
    "claude-3-5-haiku-20241022": {
        "input": 1.00 / 1_000_000,           # $1.00 per 1M tokens
        "output": 5.00 / 1_000_000,          # $5.00 per 1M tokens
        "cached_input": 0.10 / 1_000_000     # 90% discount
    },
    "claude-3-5-sonnet-20241022": {
        "input": 3.00 / 1_000_000,           # $3.00 per 1M tokens
        "output": 15.00 / 1_000_000,         # $15.00 per 1M tokens
        "cached_input": 0.30 / 1_000_000     # 90% discount
    }
}

# Voyage AI (embeddings)
VOYAGE_PRICING = {
    "voyage-3": {
        "input": 0.13 / 1_000_000            # $0.13 per 1M tokens
    },
    "voyage-3-lite": {
        "input": 0.08 / 1_000_000            # $0.08 per 1M tokens
    }
}

# Cohere (reranking)
COHERE_PRICING = {
    "rerank-v3.5": 2.00 / 1000               # $2.00 per 1K searches
}


def calculate_cost(
    input_tokens: int,
    output_tokens: int,
    model: str,
    cached_input_tokens: int = 0,
    is_audio_input: bool = False,
    is_audio_output: bool = False
) -> float:
    """
    Calculate cost in USD for an LLM call

    Args:
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        model: Model name (e.g., "gpt-4o", "gpt-4o-mini", "claude-3-5-haiku-20241022")
        cached_input_tokens: Number of cached input tokens (for prompt caching)
        is_audio_input: Whether input is audio (for Realtime API)
        is_audio_output: Whether output is audio (for Realtime API)

    Returns:
        Cost in USD
    """
    # Try OpenAI pricing first
    if model in OPENAI_PRICING:
        pricing = OPENAI_PRICING[model]
        cost = 0.0

        # Input cost
        if "realtime" in model and is_audio_input:
            cost += input_tokens * pricing["audio_input"]
        elif cached_input_tokens > 0:
            # Calculate cost for non-cached tokens
            cost += (input_tokens - cached_input_tokens) * pricing["input"]
            # Calculate cost for cached tokens (discounted)
            cost += cached_input_tokens * pricing.get("cached_input", pricing["input"])
        else:
            cost += input_tokens * pricing["input"]

        # Output cost
        if "realtime" in model and is_audio_output:
            cost += output_tokens * pricing["audio_output"]
        else:
            cost += output_tokens * pricing["output"]

        return cost

    # Try Anthropic pricing
    elif model in ANTHROPIC_PRICING:
        pricing = ANTHROPIC_PRICING[model]
        cost = 0.0

        if cached_input_tokens > 0:
            cost += (input_tokens - cached_input_tokens) * pricing["input"]
            cost += cached_input_tokens * pricing["cached_input"]
        else:
            cost += input_tokens * pricing["input"]

        cost += output_tokens * pricing["output"]
        return cost

    else:
        return 0.0  # Unknown model


def calculate_rag_retrieval_cost(
    query_tokens: int = 50,
    num_documents_reranked: int = 20
) -> float:
    """
    Calculate cost for RAG retrieval (embedding + reranking)

    Args:
        query_tokens: Number of tokens in query
        num_documents_reranked: Number of documents sent to reranker

    Returns:
        Cost in USD
    """
    # Voyage AI embedding cost
    embedding_cost = query_tokens * VOYAGE_PRICING["voyage-3"]["input"]

    # Cohere reranking cost (per search, not per document)
    reranking_cost = COHERE_PRICING["rerank-v3.5"] / 1000

    return embedding_cost + reranking_cost
