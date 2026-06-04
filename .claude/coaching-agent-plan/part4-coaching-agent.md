# Part 4: Voice Agent Diagnosis Handler

## Goal
Handle the new `diagnosis_complete` IPC message on the voice agent side. Feed the structured diagnosis results to the LLM so it can deliver a natural, data-driven coaching recap at the end of each set.

## How it fits
The orchestrator already speaks a set recap at set end (`_speak_llm_set_recap`). That recap uses basic stats (rep count, clean reps, avg depth, fault counts). Now we have much richer data — tiered root causes, specific parameter adjustments ("widen stance 10°"), per-dimension scores, trend analysis. The diagnosis results should be woven into the existing set recap flow, not replace it.

## Files to modify

### `src/services/coaching_service.py`

**Add handler in `_handle_message()`:**
- New `elif msg_type == "diagnosis_complete":` branch
- Extract diagnosis and scoring data from message
- Forward to orchestrator via a new method (below)
- The `diagnosis_complete` message arrives after `set_complete` (both sent at set end from the pipeline). The orchestrator needs to receive it before speaking the recap.

**Timing consideration:**
The `set_complete` message currently triggers the orchestrator's set recap flow. The `diagnosis_complete` message arrives separately (same set end, but a separate IPC send). Two approaches:
1. **Buffer approach:** CoachingService holds the diagnosis data and attaches it to the next set recap. The orchestrator's `on_set_complete` already receives a `set_data` dict — enrich it with diagnosis fields.
2. **Direct approach:** Orchestrator stores the latest diagnosis and pulls it into the recap prompt when it fires.

Recommend approach 2 — simpler, no timing coordination needed. The diagnosis message arrives quickly after set_complete (same `_end_current_set()` call), and the LLM recap has queue latency before it speaks.

### `src/services/coaching_orchestrator.py`

**New method: `set_diagnosis_data(diagnosis: dict, scoring: dict)`**
- Stores `_last_diagnosis` and `_last_scoring` on the orchestrator
- Cleared on `reset_set()`

**Modify `_speak_llm_set_recap()`:**
- If `_last_diagnosis` is present, enrich the LLM prompt with:
  - Top immediate cause (tier 1) — the specific cue with explanation and parameter delta
  - Session-level cause (tier 2) — the pattern to focus on
  - Composite score and per-dimension breakdown
  - Trend slope (improving / declining / stable)
  - Confidence level
- If diagnosis data is not present (pre-calibration sets, or diagnosis engine failed), fall back to existing behavior — no regression

**Modify `_speak_llm_exercise_recap()`:**
- If diagnosis data was accumulated across sets, include progression summary
- Store per-set diagnosis snapshots in `_all_set_summaries` for this purpose

**Prompt structure for the LLM:**
```
Your athlete just finished set {N}. Here's what the analysis found:

FORM SCORE: {composite}/100 (depth: {depth}, trunk control: {trunk}, knee tracking: {knee}, symmetry: {sym})
TREND: {improving/declining/stable} over the set

TOP ISSUE: {tier-1 cause explanation with specific numbers}
ADJUSTMENT: {parameter_delta in plain language, e.g. "widen stance by ~15%"}

SESSION PATTERN: {tier-2 cause if present}

Give honest, encouraging feedback (2-3 sentences). Lead with the score, give the ONE specific adjustment, end on what went well.
```

## What this does NOT do
- No per-rep coaching agent. The diagnosis runs on the pipeline side and results arrive once per set.
- No `CoachingAgent` class or new agent type. The existing orchestrator + LLM flow handles it.
- No coaching mode toggle on the orchestrator. The existing flow continues — it's just enriched with better data.

## Verification
- Send a mock `diagnosis_complete` IPC message → verify orchestrator stores it
- Trigger a set recap → verify LLM prompt includes diagnosis data
- Verify recap without diagnosis data (no calibration) → existing behavior unchanged
- Verify exercise recap includes cross-set diagnosis progression
- Listen to the spoken recap — does it reference specific numbers and adjustments?
