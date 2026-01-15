Here are the exact changes I made to migrate from GPT 5.2 to Claude Sonnet 4.5:
1. File: src/api/services/program_generator_v2.py
Import Changes (Lines 1-30)
# OLD:
from openai import AsyncOpenAI

# NEW:
from anthropic import AsyncAnthropic
import json  # Added for potential JSON handling
Docstring Update (Lines 1-10)
# OLD:
"""Uses OpenAI Structured Outputs + Knowledge Retrieval..."""

# NEW:
"""Uses Claude Opus 4.5 Tool Use + Knowledge Retrieval..."""
Client Initialization (Lines 913-914)
# OLD:
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
model = os.getenv("PROGRAM_CREATION_MODEL", "gpt-4o")

# NEW:
client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
model = os.getenv("PROGRAM_CREATION_MODEL", "claude-sonnet-4-5-20250929")
API Call - Complete Replacement (Lines 1034-1127)
# OLD (OpenAI's .parse() method):
response = await client.beta.chat.completions.parse(
    model=model,
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ],
    response_format=ProgramBatchSchema,
    timeout=480.0
)

# NEW (Claude's tool use pattern):
response = await client.messages.create(
    model=model,
    max_tokens=16384,
    system=[
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"}  # Prompt caching!
        }
    ],
    messages=[
        {"role": "user", "content": user_prompt}
    ],
    tools=[
        {
            "name": "return_program",
            "description": "Return the generated training program with all weeks and workouts",
            "input_schema": ProgramBatchSchema.model_json_schema()
        }
    ],
    tool_choice={"type": "tool", "name": "return_program"},
    timeout=480.0
)
Response Parsing (Lines 1072-1083)
# OLD (OpenAI):
return response.choices[0].message.parsed

# NEW (Claude - extract from tool use):
tool_use_block = None
for block in response.content:
    if block.type == "tool_use" and block.name == "return_program":
        tool_use_block = block
        break

if not tool_use_block:
    raise ValueError("No tool_use block found in Claude response")

parsed_data = ProgramBatchSchema.model_validate(tool_use_block.input)
return parsed_data
Token Tracking (Lines 1085-1101)
# OLD (OpenAI format):
usage = response.usage
cached_tokens = getattr(usage.prompt_tokens_details, 'cached_tokens', 0)

# NEW (Claude format):
usage = response.usage
input_tokens = usage.input_tokens
output_tokens = usage.output_tokens
cache_creation_tokens = getattr(usage, 'cache_creation_input_tokens', 0) or 0
cache_read_tokens = getattr(usage, 'cache_read_input_tokens', 0) or 0
total_tokens = input_tokens + output_tokens
Comment Updates (Lines 176, 891-894)
# OLD:
"# This prevents hitting the 16,384 token output limit on gpt-4o"
"- Batch 1: System prompt sent (3,000 tokens) → cached by OpenAI"
"- Batch 2+: System prompt retrieved from cache → 50% cost + faster!"

# NEW:
"# This prevents hitting output token limits and ensures faster generation"
"- Batch 1: System prompt sent (3,000 tokens) → cached by Claude"
"- Batch 2+: System prompt retrieved from cache → 90% cost reduction + faster!"
2. File: .env
Model Configuration (Line 14)
# OLD:
PROGRAM_CREATION_MODEL=gpt-5.2

# NEW:
PROGRAM_CREATION_MODEL=claude-sonnet-4-5-20250929
3. Package Installation
pip install anthropic
Summary of Technical Changes
Aspect	Before	After
SDK	openai	anthropic
Client	AsyncOpenAI	AsyncAnthropic
API Key	OPENAI_API_KEY	ANTHROPIC_API_KEY
Model	gpt-5.2	claude-sonnet-4-5-20250929
Structured Output	.parse() with response_format	Tool use with tools + tool_choice
Prompt Caching	Automatic (OpenAI)	cache_control: {"type": "ephemeral"}
Token Fields	prompt_tokens, completion_tokens, cached_tokens	input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens
Response Path	response.choices[0].message.parsed	response.content[i].input (tool use block)
Cache Savings	50%	90%
That's it - those are the exact changes needed to migrate from OpenAI to Claude!