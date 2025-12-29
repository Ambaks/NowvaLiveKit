# Context Summarization Implementation Request

## Background

We're building a voice agent for fitness program creation that asks ~10 questions. The conversation was hitting **context window exhaustion** in the OpenAI Realtime API (28,672 token limit for input).

### What We've Done So Far

1. **Optimized the prompt** - Reduced from ~4,033 tokens to ~2,495 tokens (38% reduction)
2. **Fixed truncation API** - Corrected implementation to use `context.session.current_agent` instead of `context.agent`
3. **Added strategic truncation** - Truncate conversation at 3 milestones during data collection

### Current Truncation Problem

The current implementation just **deletes old messages**, which loses context:
- Agent might ask duplicate questions
- Doesn't remember what was already collected
- Conversation history is completely gone

## What We Want to Implement

**LLM-based conversation summarization** - Instead of deleting old messages, use an LLM to summarize them into a concise sentence that preserves context.

### Key Requirements

1. **When to summarize**: When conversation exceeds `max_items` (default: 10 messages)
2. **What to summarize**: The oldest messages that will be truncated
3. **How to summarize**: Call OpenAI API (gpt-4o-mini) to generate 1-sentence summary
4. **What to keep**: Summary + last N recent messages
5. **Fallback**: If LLM call fails, use simple state-based summary

### Example Flow

**Before truncation** (20 messages, ~2000 tokens):
```
User: "5'10 and 175 pounds"
Agent: "Got it, capturing height and weight"
[function call: capture_height_weight...]
User: "I'm 28 years old, male"
Agent: "Perfect, noted your age and sex"
[function call: capture_age_sex...]
User: "I want to get stronger"
Agent: "Excellent, strength training focus"
[more messages...]
```

**After LLM summarization** (1 summary + 8 recent, ~400 tokens):
```
SYSTEM: "User is 178cm, 79kg, 28-year-old male with a strength training goal."
[last 8 recent messages only...]
```

### Benefits

- ✅ **Context preserved**: Agent knows what's been collected
- ✅ **No duplicate questions**: Summary shows height/weight already captured
- ✅ **Natural language**: LLM generates human-readable summary
- ✅ **Token efficient**: 1 sentence vs 12+ messages
- ✅ **Smart**: LLM combines related info intelligently

## Implementation Plan

### Location
**File**: `/Users/naiahoard/NowvaLiveKit/src/agents/voice_agent.py`

### Changes Needed

1. **Update `_truncate_conversation_history()` method** (lines ~177-224)
   - Add LLM summarization step before truncation
   - Create new context with summary + recent messages
   - Insert summary as system message

2. **Add new helper method `_generate_conversation_summary()`**
   - Takes conversation items to summarize
   - Calls OpenAI API to generate summary
   - Returns 1-sentence summary string
   - Has fallback if API call fails

3. **Add fallback method `_build_simple_summary()`**
   - Builds summary from agent state if LLM fails
   - Simple format: "Collected: height 178cm, weight 79kg, goal: strength"

### Technical Details

**LLM Summarization Call**:
- Model: `gpt-4o-mini` (fast and cheap)
- Temperature: 0.3 (focused and consistent)
- Max tokens: 100 (keep it concise)
- Prompt: "Summarize this conversation into ONE concise sentence focusing on what data was collected (height, weight, age, goals, etc). Be specific with numbers."

**Context Update**:
- Use `context.session.current_agent` to get agent
- Create new `ChatContext.empty()`
- Add summary as system message
- Insert recent messages
- Call `await agent.update_chat_ctx(new_ctx)`

### Code Structure

```python
async def _truncate_conversation_history(self, context, max_items=10):
    # 1. Get agent and chat context
    # 2. Check if truncation needed
    # 3. Split into old (to summarize) and recent (to keep)
    # 4. Generate LLM summary of old messages
    # 5. Create new context: summary + recent messages
    # 6. Update agent context

async def _generate_conversation_summary(self, items):
    # 1. Convert items to text format
    # 2. Call OpenAI API with summarization prompt
    # 3. Return summary string
    # 4. Fallback to simple summary if fails

def _build_simple_summary(self):
    # 1. Read from agent state
    # 2. Format as: "Collected: height Xcm, weight Ykg, goal: Z"
    # 3. Return string
```

## What We Need from Claude Code

Please implement this LLM-based conversation summarization system with the following:

1. Complete implementation of all three methods
2. Proper error handling and fallbacks
3. Good logging for debugging
4. Integration with existing truncation call sites (already in place)
5. Make sure it works with LiveKit's Realtime API architecture

The goal is to have the agent maintain context throughout the entire 10-question flow without hitting the 28K token limit, while preserving important information about what's been collected.
