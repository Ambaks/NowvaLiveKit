"""
Pricing Configuration for All AI Services
Centralized pricing data for cost calculation
Updated: 2026-06-09
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
    # GPT-5 Models (preview/internal - using estimated pricing)
    "gpt-5.2": {
        "input": 3.00 / 1_000_000,       # Estimated: slightly higher than gpt-4o
        "output": 12.00 / 1_000_000,     # Estimated: slightly higher than gpt-4o
        "cached_input": 1.50 / 1_000_000 # 50% discount
    },
    "gpt-5-mini": {
        "input": 0.150 / 1_000_000,      # Same as gpt-4o-mini (per OPTIMIZATION_SUMMARY.md)
        "output": 0.600 / 1_000_000,
        "cached_input": 0.075 / 1_000_000
    },
    "gpt-5-nano": {
        "input": 0.10 / 1_000_000,       # Estimated: cheaper than mini
        "output": 0.40 / 1_000_000,
        "cached_input": 0.05 / 1_000_000
    },
    "gpt-5.4-nano": {
        "input": 0.20 / 1_000_000,       # $0.20 per 1M tokens
        "output": 1.25 / 1_000_000,      # $1.25 per 1M tokens
        "cached_input": 0.02 / 1_000_000 # $0.02 per 1M tokens
    },
    "gpt-5.4-mini": {
        "input": 0.75 / 1_000_000,       # $0.75 per 1M tokens
        "output": 4.50 / 1_000_000,      # $4.50 per 1M tokens
        "cached_input": 0.075 / 1_000_000 # $0.075 per 1M tokens
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

# Google Gemini (cascade pipeline LLM)
GOOGLE_PRICING = {
    "gemini-3.1-flash-lite": {
        "input": 0.10 / 1_000_000,           # $0.10 per 1M tokens (est.)
        "output": 0.40 / 1_000_000,          # $0.40 per 1M tokens (est.)
        "cached_input": 0.025 / 1_000_000,   # 75% discount (est.)
    },
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
        model: Model name (e.g., "gpt-4o", "gpt-5.2", "groq-llama-3.3-70b", "claude-3-5-haiku-20241022")
        cached_input_tokens: Number of cached input tokens (for prompt caching)
        is_audio_input: Deprecated, kept for backwards compatibility
        is_audio_output: Deprecated, kept for backwards compatibility

    Returns:
        Cost in USD
    """
    # Try OpenAI pricing first
    if model in OPENAI_PRICING:
        pricing = OPENAI_PRICING[model]
        cost = 0.0

        # Input cost
        if cached_input_tokens > 0:
            cost += (input_tokens - cached_input_tokens) * pricing["input"]
            cost += cached_input_tokens * pricing.get("cached_input", pricing["input"])
        else:
            cost += input_tokens * pricing["input"]

        # Output cost
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

    # Try Google Gemini pricing
    elif model in GOOGLE_PRICING:
        pricing = GOOGLE_PRICING[model]
        cost = 0.0

        if cached_input_tokens > 0:
            cost += (input_tokens - cached_input_tokens) * pricing["input"]
            cost += cached_input_tokens * pricing.get("cached_input", pricing["input"])
        else:
            cost += input_tokens * pricing["input"]

        cost += output_tokens * pricing["output"]
        return cost

    else:
        # Unknown model - use GPT-4o pricing as fallback estimate
        print(f"⚠️  Warning: Unknown model '{model}' - using GPT-4o pricing as estimate")
        pricing = OPENAI_PRICING["gpt-4o"]
        cost = 0.0

        if cached_input_tokens > 0:
            cost += (input_tokens - cached_input_tokens) * pricing["input"]
            cost += cached_input_tokens * pricing.get("cached_input", pricing["input"])
        else:
            cost += input_tokens * pricing["input"]

        cost += output_tokens * pricing["output"]
        return cost


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

    reranking_cost = COHERE_PRICING["rerank-v3.5"]

    return embedding_cost + reranking_cost
