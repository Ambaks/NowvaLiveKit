"""
Token Estimation Utilities
Estimates token counts when actual usage is unavailable
"""

import tiktoken
import json
from typing import Any, Dict, Tuple

# Token estimation rates (tokens per second)
REALTIME_AUDIO_INPUT_RATE = 50   # Conservative estimate
REALTIME_AUDIO_OUTPUT_RATE = 75  # Includes TTS overhead


def estimate_text_tokens(text: str, model: str = "gpt-4o") -> int:
    """
    Estimate tokens for text using tiktoken

    Args:
        text: The text to estimate tokens for
        model: Model name for encoding (default: gpt-4o)

    Returns:
        Estimated token count
    """
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        # Fallback to cl100k_base for unknown models
        encoding = tiktoken.get_encoding("cl100k_base")

    return len(encoding.encode(text))


def estimate_audio_tokens(duration_seconds: float, is_input: bool = True) -> int:
    """
    Estimate tokens for audio based on duration

    Args:
        duration_seconds: Audio duration in seconds
        is_input: Whether this is input audio (vs output)

    Returns:
        Estimated token count
    """
    rate = REALTIME_AUDIO_INPUT_RATE if is_input else REALTIME_AUDIO_OUTPUT_RATE
    return int(duration_seconds * rate)


def estimate_function_call_tokens(
    function_name: str,
    parameters: Dict[str, Any],
    result: Any
) -> Tuple[int, int]:
    """
    Estimate tokens for function call (input) and result (output)

    Args:
        function_name: Name of the function called
        parameters: Function parameters as dict
        result: Function return value

    Returns:
        Tuple of (input_tokens, output_tokens)
    """
    # Function call overhead: name + parameters as JSON
    input_json = json.dumps({
        "function": function_name,
        "parameters": parameters
    })
    input_tokens = estimate_text_tokens(input_json)

    # Result tokens
    if result is None:
        output_tokens = 5  # Minimal
    else:
        result_json = json.dumps({"result": str(result)})
        output_tokens = estimate_text_tokens(result_json)

    return (input_tokens, output_tokens)
