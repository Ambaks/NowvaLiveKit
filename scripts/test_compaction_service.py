#!/usr/bin/env python3
"""
Test script for CompactionService.

Simulates a workout conversation with 50+ events, runs multiple compaction
cycles, and verifies:
- Event buffering
- 3-tier summary generation (hot/warm/cold)
- ISO timestamps in all entries
- Time-decay (hot -> warm -> cold)
- Cold flush to memory.md when threshold exceeded
- Pointer replacement after flush
- Session folder structure (memory.md + session_meta.json)
- Final metadata on stop()
- Cost tracking

Does NOT require LiveKit or Realtime API — uses mocked event data.
"""

import asyncio
import json
import os
import sys
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
from dataclasses import dataclass

# Add src/ to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ---------------------------------------------------------------------------
# Mock classes
# ---------------------------------------------------------------------------

class MockAgentState:
    def get_mode(self):
        return "workout"


@dataclass
class MockConversationItem:
    role: str
    _text: str

    def text_content(self):
        return self._text


@dataclass
class MockConversationEvent:
    item: MockConversationItem


@dataclass
class MockFunctionCall:
    name: str
    arguments: str


@dataclass
class MockFunctionOutput:
    output: str


class MockToolEvent:
    def __init__(self, calls_and_outputs):
        self._pairs = calls_and_outputs

    def zipped(self):
        return self._pairs


class MockUsage:
    def __init__(self, prompt_tokens=150, completion_tokens=80):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class MockChoice:
    def __init__(self, content):
        self.message = MagicMock(content=content)


class MockResponse:
    def __init__(self, content, prompt_tokens=150, completion_tokens=80):
        self.choices = [MockChoice(content)]
        self.usage = MockUsage(prompt_tokens, completion_tokens)


class MockSession:
    """Simulates AgentSession with on/off event registration."""
    def __init__(self):
        self._listeners = {}

    def on(self, event_name, handler):
        self._listeners.setdefault(event_name, []).append(handler)

    def off(self, event_name, handler):
        if event_name in self._listeners:
            self._listeners[event_name] = [h for h in self._listeners[event_name] if h != handler]

    def emit(self, event_name, ev):
        for handler in self._listeners.get(event_name, []):
            handler(ev)


# ---------------------------------------------------------------------------
# Simulated workout events
# ---------------------------------------------------------------------------

def generate_workout_events():
    """Generate 55+ realistic workout events."""
    events = []

    # Warm-up phase (older events)
    events.append(("user", "Hey Nova, I'm ready to start my workout"))
    events.append(("assistant", "Great! Let's get started with your push day workout. First up is bench press, 4 sets of 8 reps at 70 kilograms."))
    events.append(("user", "Sounds good, let me set up"))
    events.append(("assistant", "Take your time. When you're ready, I'll start the timer."))

    # Bench press sets
    for s in range(1, 5):
        events.append(("user", f"Done with set {s}"))
        events.append(("tool_call", f"log_set_complete(exercise='bench_press', set={s}, reps=8, weight=70)"))
        events.append(("tool_result", f"Set {s}/4 logged: bench press 8 reps @ 70kg"))
        events.append(("assistant", f"Nice work on set {s}! {'Rest for 90 seconds.' if s < 4 else 'Bench press complete! Moving on to overhead press.'}"))

    # Overhead press sets
    events.append(("user", "What's next?"))
    events.append(("assistant", "Next exercise is overhead press. 3 sets of 10 at 40 kilograms."))
    for s in range(1, 4):
        events.append(("user", f"Set {s} done"))
        events.append(("tool_call", f"log_set_complete(exercise='overhead_press', set={s}, reps=10, weight=40)"))
        events.append(("tool_result", f"Set {s}/3 logged: overhead press 10 reps @ 40kg"))
        if s == 2:
            events.append(("user", "My left shoulder feels a bit tight"))
            events.append(("assistant", "Thanks for letting me know. Make sure to keep your elbows slightly in front of the bar. If the tightness increases or becomes painful, we should stop and switch to a lateral raise instead."))
        else:
            events.append(("assistant", f"Set {s} logged! {'Keep it up!' if s < 3 else 'Overhead press done!'}"))

    # Progress check
    events.append(("user", "How many sets do I have left?"))
    events.append(("tool_call", "get_workout_progress()"))
    events.append(("tool_result", "completed 7/12 sets (58%). Remaining: lateral raise 3x12@10kg, tricep pushdown 2x15"))
    events.append(("assistant", "You're 58% done! 7 of 12 sets complete. You've got lateral raises 3 sets of 12 at 10 kilograms, then tricep pushdowns 2 sets of 15."))

    # Lateral raises
    events.append(("user", "Let's go"))
    for s in range(1, 4):
        events.append(("tool_call", f"log_set_complete(exercise='lateral_raise', set={s}, reps=12, weight=10)"))
        events.append(("tool_result", f"Set {s}/3 logged: lateral raise 12 reps @ 10kg"))
        events.append(("assistant", f"Lateral raise set {s} done."))

    # Tricep pushdowns
    for s in range(1, 3):
        events.append(("tool_call", f"log_set_complete(exercise='tricep_pushdown', set={s}, reps=15, weight=25)"))
        events.append(("tool_result", f"Set {s}/2 logged: tricep pushdown 15 reps @ 25kg"))
        events.append(("assistant", f"Tricep pushdown set {s} complete."))

    # Schedule request
    events.append(("user", "Can you check my schedule for tomorrow?"))
    events.append(("assistant", "Sure! After we finish, I'll pull up your schedule."))

    return events


# ---------------------------------------------------------------------------
# LLM response generator (mock)
# ---------------------------------------------------------------------------

CYCLE_RESPONSES = [
    # Cycle 1 — early workout
    """[HOT]
[14:05:12] User started workout and is setting up for bench press. [14:05:15] Nova announced push day: bench press 4x8@70kg first.

[WARM]
(empty — first cycle)

[COLD]
(empty — first cycle)""",

    # Cycle 2 — bench press in progress
    """[HOT]
[14:08:30] User completed bench press set 3/4 at 70kg, 8 reps each. [14:08:35] Nova encouraged user and noted rest period.

[WARM]
[14:05:00-14:07:00] User started push day workout. Bench press sets 1-2 completed: 8 reps at 70kg each, good form.

[COLD]
(empty — session just started)""",

    # Cycle 3 — bench press done, starting overhead press
    """[HOT]
[14:12:10] Starting overhead press: 3 sets of 10 at 40kg. [14:12:15] User asked what's next after completing bench press.

[WARM]
[14:08:00-14:11:00] Bench press sets 3-4 completed. All 4 sets of 8 reps at 70kg done with clean form.

[COLD]
[14:05:00-14:08:00] Completed bench press 4x8@70kg. User was enthusiastic at start of push day workout.""",

    # Cycle 4 — overhead press with shoulder concern
    """[HOT]
[14:16:20] User reported left shoulder tightness during overhead press set 2. [14:16:25] Nova advised keeping elbows slightly in front and offered lateral raise alternative if pain increases.

[WARM]
[14:12:00-14:15:00] Overhead press sets 1-2 completed: 10 reps at 40kg. User performing well overall.

[COLD]
[14:05:00-14:12:00] Completed bench press 4x8@70kg with clean form. Started overhead press 3x10@40kg.""",

    # Cycle 5 — progress check, moving to lateral raises
    """[HOT]
[14:20:00] User asked about remaining sets. 7/12 sets done (58%). [14:20:05] Remaining: lateral raise 3x12@10kg, tricep pushdown 2x15.

[WARM]
[14:12:00-14:19:00] Overhead press 3x10@40kg completed. User had left shoulder tightness on set 2 — advised form correction, did not need to switch exercises.

[COLD]
[14:05:00-14:12:00] Completed bench press 4x8@70kg with clean form. User was enthusiastic at start of push day workout.""",

    # Cycle 6 — lateral raises and triceps done
    """[HOT]
[14:25:30] Tricep pushdown set 2 complete. [14:25:35] User asked about tomorrow's schedule. Nova will check after workout finishes.

[WARM]
[14:20:00-14:24:00] Lateral raise 3x12@10kg completed. Tricep pushdown 2x15@25kg completed. Workout nearly done — 12/12 sets.

[COLD]
[14:05:00-14:12:00] Completed bench press 4x8@70kg with clean form.
[14:12:00-14:19:00] Completed overhead press 3x10@40kg. Left shoulder tightness noted on set 2 — form adjusted, no exercise swap needed.
[14:19:00-14:20:00] Progress check at 58% (7/12 sets). User requested schedule review after workout.""",

    # Cycle 7 — generates a lot of cold (for flush testing)
    """[HOT]
[14:28:00] Workout complete. User resting and waiting for schedule review.

[WARM]
[14:25:00-14:27:00] Final two tricep pushdown sets completed. All 12 sets done. User satisfied with session.

[COLD]
[14:05:00-14:12:00] Completed bench press 4x8@70kg with clean form. User started enthusiastically.
[14:12:00-14:19:00] Completed overhead press 3x10@40kg. Left shoulder tightness noted on set 2, form correction applied, no exercise swap needed. Safety flag: monitor left shoulder in future sessions.
[14:19:00-14:20:00] Progress check at 58% (7/12 sets). User requested schedule review after workout.
[14:20:00-14:24:00] Completed lateral raise 3x12@10kg with good form and controlled tempo.
[14:24:00-14:27:00] Completed tricep pushdown 2x15@25kg. Full pump achieved. Workout complete.
[14:27:00-14:28:00] User asked about tomorrow's schedule. Nova acknowledged and will check after cooldown. Pending action: schedule review for tomorrow.
Extra filler to push past the cold flush threshold. The user had an excellent workout with consistent form across all exercises. Total volume: bench press 2240kg, overhead press 1200kg, lateral raise 360kg, tricep pushdown 750kg. Overall workout rating: 8/10. The left shoulder tightness was managed well and did not impact performance significantly. Recommend monitoring in next session and possibly adding shoulder mobility warm-up.""",
]


def make_mock_openai_client(responses):
    """Create a mock OpenAI client that returns predefined responses."""
    client = MagicMock()
    call_count = [0]

    def create(**kwargs):
        idx = min(call_count[0], len(responses) - 1)
        call_count[0] += 1
        return MockResponse(responses[idx])

    client.chat.completions.create = create
    return client


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

async def run_tests():
    print("=" * 70)
    print("CompactionService Test Suite")
    print("=" * 70)

    # Use temp directory for session logs
    tmp_dir = tempfile.mkdtemp(prefix="compaction_test_")
    print(f"\nTest session dir: {tmp_dir}")

    from services.compaction_service import CompactionService

    session = MockSession()
    state = MockAgentState()
    mock_client = make_mock_openai_client(CYCLE_RESPONSES)

    service = CompactionService(
        session=session,
        state=state,
        user_id="test_user_123",
        model="gpt-4.1-mini",
        interval_seconds=5.0,
        cold_flush_threshold=150,  # lower threshold to trigger flush in test
        openai_client=mock_client,
    )

    passed = 0
    failed = 0

    def check(name, condition, detail=""):
        nonlocal passed, failed
        if condition:
            print(f"  PASS: {name}")
            passed += 1
        else:
            print(f"  FAIL: {name} {detail}")
            failed += 1

    # ------------------------------------------------------------------
    # Test 1: Start & session folder
    # ------------------------------------------------------------------
    print("\n--- Test 1: Start & Session Folder ---")

    # Point session logs to temp dir via env var
    with patch.dict(os.environ, {"COMPACTION_SESSION_LOG_DIR": tmp_dir}):
        await service.start()

    check("Service is running", service._running)
    check("Session dir created", service._session_dir is not None and service._session_dir.exists())
    check("memory.md exists", service._memory_path is not None and service._memory_path.exists())

    if service._memory_path and service._memory_path.exists():
        mem_content = service._memory_path.read_text()
        check("memory.md has header", "# Nova Session Memory" in mem_content)
        check("memory.md has user_id", "test_user_123" in mem_content)

    meta_path = service._session_dir / "session_meta.json" if service._session_dir else None
    check("session_meta.json exists", meta_path and meta_path.exists())
    if meta_path and meta_path.exists():
        meta = json.loads(meta_path.read_text())
        check("meta has user_id", meta.get("user_id") == "test_user_123")
        check("meta has initial_mode", meta.get("initial_mode") == "workout")

    # ------------------------------------------------------------------
    # Test 2: Event buffering
    # ------------------------------------------------------------------
    print("\n--- Test 2: Event Buffering ---")

    events = generate_workout_events()
    check("Generated 50+ events", len(events) >= 50, f"(got {len(events)})")

    # Cancel the background task so we control compaction manually
    if service._task:
        service._task.cancel()
        try:
            await service._task
        except asyncio.CancelledError:
            pass

    # Feed events in batches
    batch_size = 8
    for i in range(0, len(events), batch_size):
        batch = events[i:i + batch_size]
        for role, content in batch:
            if role == "tool_call":
                # Parse tool call
                name = content.split("(")[0]
                args = content[len(name):]
                ev = MockToolEvent([
                    (MockFunctionCall(name, args), MockFunctionOutput(f"Result: {args}"))
                ])
                session.emit("function_tools_executed", ev)
            elif role == "tool_result":
                # Tool results are already captured by tool_call handler
                pass
            else:
                item = MockConversationItem(role=role, _text=content)
                ev = MockConversationEvent(item=item)
                session.emit("conversation_item_added", ev)

    buf_size = service.get_event_buffer_size()
    check("Events buffered", buf_size > 0, f"(buf={buf_size})")

    # Check buffer entries have required fields
    if service._event_buffer:
        entry = service._event_buffer[0]
        check("Buffer entry has timestamp", "timestamp" in entry)
        check("Buffer entry has iso_timestamp", "iso_timestamp" in entry)
        check("Buffer entry has role", "role" in entry)
        check("Buffer entry has content", "content" in entry)
        check("Buffer entry has event_type", "event_type" in entry)

    # ------------------------------------------------------------------
    # Test 3: Compaction cycles
    # ------------------------------------------------------------------
    print("\n--- Test 3: Compaction Cycles ---")

    # Run cycle 1
    await service._run_compaction_cycle()
    check("Cycle 1 completed", service._cycle_count == 1)
    check("Hot is non-empty", len(service._hot) > 0)
    check("Buffer cleared after cycle", service.get_event_buffer_size() == 0)

    print(f"\n  [Cycle 1 Output]")
    print(f"  HOT:  {service._hot[:120]}...")
    print(f"  WARM: {service._warm[:120] if service._warm else '(empty)'}")
    print(f"  COLD: {service._cold[:120] if service._cold else '(empty)'}")

    # Feed more events and run more cycles
    for cycle_num in range(2, 8):
        # Add a few events per cycle
        start_idx = min(cycle_num * 5, len(events) - 1)
        end_idx = min(start_idx + 5, len(events))
        for role, content in events[start_idx:end_idx]:
            if role not in ("tool_call", "tool_result"):
                item = MockConversationItem(role=role, _text=content)
                ev = MockConversationEvent(item=item)
                session.emit("conversation_item_added", ev)

        if service.get_event_buffer_size() == 0:
            # Add a dummy event so the cycle runs
            item = MockConversationItem(role="user", _text=f"Cycle {cycle_num} dummy event")
            ev = MockConversationEvent(item=item)
            session.emit("conversation_item_added", ev)

        await service._run_compaction_cycle()

        print(f"\n  [Cycle {cycle_num} Output]")
        print(f"  HOT:  {service._hot[:120]}...")
        print(f"  WARM: {service._warm[:120] if service._warm else '(empty)'}")
        print(f"  COLD: {service._cold[:120] if service._cold else '(empty)'}")

    check("Multiple cycles completed", service._cycle_count >= 5, f"(got {service._cycle_count})")

    # ------------------------------------------------------------------
    # Test 4: Timestamps in summaries
    # ------------------------------------------------------------------
    print("\n--- Test 4: Timestamps in Summaries ---")

    # Check for timestamp patterns like [HH:MM:SS] or [HH:MM:SS-HH:MM:SS]
    import re
    ts_pattern = re.compile(r'\[\d{2}:\d{2}(:\d{2})?\]|\[\d{2}:\d{2}(:\d{2})?-\d{2}:\d{2}(:\d{2})?\]')

    hot_has_ts = bool(ts_pattern.search(service._hot)) if service._hot else True
    check("Hot has timestamps", hot_has_ts, f"hot='{service._hot[:100]}'")

    warm_has_ts = bool(ts_pattern.search(service._warm)) if service._warm else True
    check("Warm has timestamps", warm_has_ts, f"warm='{service._warm[:100]}'")

    # Cold might have pointer or timestamps
    cold_has_ts = bool(ts_pattern.search(service._cold)) or "flushed" in service._cold.lower() if service._cold else True
    check("Cold has timestamps or pointer", cold_has_ts, f"cold='{service._cold[:100]}'")

    # ------------------------------------------------------------------
    # Test 5: get_summary()
    # ------------------------------------------------------------------
    print("\n--- Test 5: get_summary() ---")

    summary = service.get_summary()
    check("Summary is non-empty", len(summary) > 0)
    check("Summary contains SESSION CONTEXT", "[SESSION CONTEXT]" in summary or not service._cold)
    check("Summary contains RECENT CONTEXT", "[RECENT CONTEXT]" in summary or not service._hot)

    print(f"\n  Full summary ({len(summary)} chars):")
    for line in summary.split("\n"):
        print(f"    {line}")

    # ------------------------------------------------------------------
    # Test 6: Cold flush to memory.md
    # ------------------------------------------------------------------
    print("\n--- Test 6: Cold Flush ---")

    check("Cold flush occurred", service._cold_flush_count > 0,
          f"(count={service._cold_flush_count}, cold_len={len(service._cold.split())} words)")

    if service._cold_flush_count > 0:
        check("Cold contains pointer", "flushed" in service._cold.lower(),
              f"cold='{service._cold[:120]}'")
        check("Pointer has flush count", str(service._cold_flush_count) in service._cold)

        if service._memory_path and service._memory_path.exists():
            mem = service._memory_path.read_text()
            check("memory.md has flush section", "## Context flushed at" in mem)
            check("memory.md has separator", "---" in mem)

            print(f"\n  memory.md content ({len(mem)} chars):")
            for line in mem.split("\n")[:30]:
                print(f"    {line}")
            if mem.count("\n") > 30:
                print(f"    ... ({mem.count(chr(10)) - 30} more lines)")

    # Force a second flush to test accumulation
    if service._cold_flush_count == 1:
        # Manually set cold to exceed threshold
        service._cold = (
            service._cold + "\n" +
            "Additional cold context that should trigger a second flush. " * 30
        )
        estimated = int(len(service._cold.split()) * 1.3)
        if estimated > service._cold_flush_threshold:
            await service._flush_cold_to_memory()
            check("Second flush occurred", service._cold_flush_count == 2)
            if service._memory_path and service._memory_path.exists():
                mem2 = service._memory_path.read_text()
                flush_count = mem2.count("## Context flushed at")
                check("memory.md has 2 flush sections", flush_count >= 2,
                      f"(found {flush_count})")

    # ------------------------------------------------------------------
    # Test 7: Cost tracking
    # ------------------------------------------------------------------
    print("\n--- Test 7: Cost Tracking ---")

    stats = service.get_stats()
    check("Stats has cost", stats["total_cost_usd"] > 0, f"(${stats['total_cost_usd']})")
    check("Stats has input tokens", stats["total_input_tokens"] > 0)
    check("Stats has output tokens", stats["total_output_tokens"] > 0)
    check("Stats has cycle count", stats["cycle_count"] == service._cycle_count)

    print(f"\n  Stats: {json.dumps(stats, indent=2)}")

    # ------------------------------------------------------------------
    # Test 8: Stop & final metadata
    # ------------------------------------------------------------------
    print("\n--- Test 8: Stop & Final Metadata ---")

    await service.stop()
    check("Service stopped", not service._running)

    if meta_path and meta_path.exists():
        final_meta = json.loads(meta_path.read_text())
        check("Final meta has session_end", "session_end" in final_meta)
        check("Final meta has total_compaction_cycles", "total_compaction_cycles" in final_meta)
        check("Final meta has total_cold_flushes", "total_cold_flushes" in final_meta)
        check("Final meta has total_events_processed", "total_events_processed" in final_meta)
        check("Final meta has estimated_cost_usd", "estimated_cost_usd" in final_meta)
        check("Final meta has final_mode", final_meta.get("final_mode") == "workout")

        print(f"\n  Final metadata:")
        print(f"  {json.dumps(final_meta, indent=2)}")

    # ------------------------------------------------------------------
    # Test 9: Lifecycle guards
    # ------------------------------------------------------------------
    print("\n--- Test 9: Lifecycle Guards ---")

    # stop() when not running should be safe
    await service.stop()
    check("Double stop() is safe", True)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print(f"Results: {passed} passed, {failed} failed out of {passed + failed} checks")
    print("=" * 70)

    # Cleanup
    try:
        shutil.rmtree(tmp_dir)
        print(f"\nCleaned up test directory: {tmp_dir}")
    except Exception as e:
        print(f"\nWarning: Failed to clean up {tmp_dir}: {e}")

    return failed == 0


if __name__ == "__main__":
    import logging
    logging.basicConfig(
        level=logging.DEBUG if os.getenv("COMPACTION_DEBUG") == "1" else logging.INFO,
        format="%(asctime)s %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
    )

    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)
