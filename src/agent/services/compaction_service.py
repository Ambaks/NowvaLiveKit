"""
Compaction Service — Rolling Background Context Summarization

Listens to AgentSession events (conversation turns, tool calls) and
periodically compacts them into a 3-tier summary (HOT / WARM / COLD)
using the Chat Completions API (GPT-4.1-mini).

When the COLD tier grows too large it is flushed to a per-session
memory.md file on disk.

The voice agent and coaching service call get_summary() to inject a
compact context window into LLM calls, avoiding unbounded token growth.
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Pricing per 1M tokens (GPT-4.1-mini)
_INPUT_COST_PER_M = 0.40
_OUTPUT_COST_PER_M = 1.60

_COMPACTION_SYSTEM_PROMPT = """\
You are a context compaction agent for a real-time fitness coaching AI.
Your job is to maintain a rolling summary of the conversation at three levels of detail.

You will receive:
1. The current summary (hot/warm/cold sections)
2. New conversation events since the last cycle (each with a timestamp)

Output EXACTLY this format (no other text):

[HOT]
<Last ~60 seconds of conversation. Keep specific details: exercise names, rep counts, weights, form feedback, user requests. 2-4 sentences max. Prefix each sentence with its timestamp in [HH:MM:SS] format.>

[WARM]
<Events from 1-10 minutes ago. Compress to key facts: sets completed, exercises done, any schedule changes or coaching tips given. 1-3 sentences max. Use timestamp ranges like [HH:MM:SS-HH:MM:SS].>

[COLD]
<Everything older than 10 minutes. One-line summaries with timestamp ranges. Example: "[14:00-14:10] Completed bench press 3x8@80kg, good form." Append to existing cold context. If cold already contains a memory.md pointer line (starts with "[Older context flushed"), preserve that pointer as the first line and only append new entries after it.>

Rules:
- EVERY entry in hot, warm, and cold MUST include a timestamp or timestamp range
- NEVER drop safety-relevant information (injuries, pain, equipment issues)
- NEVER drop user preferences or requests that haven't been addressed yet
- Preserve exact numbers: weights, reps, sets, RPE, depth angles
- When context decays from hot->warm->cold, merge and compress -- don't just copy
- If nothing meaningful happened (silence, ambient noise), output the previous summary unchanged
- If the cold section contains a "[Older context flushed to memory.md..." pointer, always keep it as the first line of cold
- Current agent mode: {mode}
"""


class CompactionService:
    """Rolling background context compaction via GPT-4.1-mini.

    Listens to conversation events from the AgentSession, accumulates
    them in a buffer, and periodically summarizes them into a 3-tier
    summary (hot/warm/cold) using the Chat Completions API.

    The summary is always pre-built and available via get_summary().
    Main agent prune/truncate methods call get_summary() instead of
    hard-truncating, injecting the summary as a context message.
    """

    def __init__(
        self,
        session,                          # AgentSession
        state,                            # AgentState
        user_id: str = "guest",
        model: str | None = None,
        interval_seconds: float | None = None,
        cold_flush_threshold: int | None = None,
        openai_client=None,
    ):
        self._session = session
        self._state = state
        self._user_id = user_id

        # Config from env vars with defaults
        self._model = model or os.getenv("COMPACTION_MODEL", "gpt-4.1-mini")
        self._interval_seconds = interval_seconds or float(os.getenv("COMPACTION_INTERVAL", "30"))
        self._cold_flush_threshold = cold_flush_threshold or int(os.getenv("COMPACTION_COLD_FLUSH_THRESHOLD", "300"))
        self._debug = os.getenv("COMPACTION_DEBUG", "0") == "1"

        # OpenAI client — lazy-initialised if not injected
        self._client = openai_client

        # State (protected by _lock)
        self._event_buffer: List[Dict[str, Any]] = []
        self._hot: str = ""
        self._warm: str = ""
        self._cold: str = ""

        # Lifecycle
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None
        self._lock: asyncio.Lock = asyncio.Lock()

        # Timing
        self._last_compaction: float = 0.0
        self._session_start_time: datetime = datetime.now(timezone.utc)

        # Counters
        self._cycle_count: int = 0
        self._cold_flush_count: int = 0
        self._total_events_processed: int = 0
        self._total_input_tokens: int = 0
        self._total_output_tokens: int = 0

        # Session folder
        self._session_dir: Optional[Path] = None
        self._memory_path: Optional[Path] = None

        # Event handlers (stored for unregistration)
        self._on_conversation = None
        self._on_tools = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Register event listeners on the session and start the background compaction loop."""
        if self._running:
            return

        self._running = True
        self._last_compaction = time.monotonic()
        self._session_start_time = datetime.now(timezone.utc)

        # Lazy-init OpenAI client
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI()
            except Exception as e:
                logger.error(f"[COMPACTION:ERROR] Failed to initialize OpenAI client: {e}")
                self._running = False
                return

        # Create session folder
        self._init_session_folder()

        # Register event listeners
        self._on_conversation = lambda ev: self._handle_conversation_item(ev)
        self._on_tools = lambda ev: self._handle_tools_executed(ev)
        self._session.on("conversation_item_added", self._on_conversation)
        self._session.on("function_tools_executed", self._on_tools)

        # Start background loop
        self._task = asyncio.create_task(self._compaction_loop())
        logger.info(
            f"[COMPACTION:SESSION] Started (model={self._model}, "
            f"interval={self._interval_seconds}s, flush_threshold={self._cold_flush_threshold})"
        )

    async def stop(self) -> None:
        """Unregister event listeners, cancel background task, write final metadata."""
        if not self._running:
            return

        self._running = False

        # Cancel background task
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        # Unregister listeners
        if self._on_conversation:
            try:
                self._session.off("conversation_item_added", self._on_conversation)
            except Exception:
                pass
        if self._on_tools:
            try:
                self._session.off("function_tools_executed", self._on_tools)
            except Exception:
                pass

        # Write final metadata
        self._write_final_metadata()

        logger.info(
            f"[COMPACTION:SESSION] Stopped — {self._cycle_count} cycles, "
            f"{self._cold_flush_count} flushes, {self._total_events_processed} events, "
            f"est. cost=${self.get_stats()['total_cost_usd']:.4f}"
        )

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _handle_conversation_item(self, ev):
        """Buffer a conversation turn (user or assistant speech)."""
        try:
            item = ev.item
            role = getattr(item, "role", "unknown")
            text = getattr(item, "text_content", None)
            if callable(text):
                text = text()
            if not text:
                return

            now = datetime.now(timezone.utc)
            entry = {
                "timestamp": time.monotonic(),
                "iso_timestamp": now.isoformat(),
                "role": role,
                "content": text[:500],
                "event_type": f"{role}_speech",
            }
            self._event_buffer.append(entry)
            self._total_events_processed += 1

            if self._debug:
                ts = now.strftime("%H:%M:%S")
                logger.debug(
                    f"[COMPACTION:EVENT] Buffered: {role}_speech [{ts}] "
                    f"\"{text[:80]}\" (buf={len(self._event_buffer)})"
                )
        except Exception as e:
            logger.error(f"[COMPACTION:ERROR] Failed to buffer conversation item: {e}")

    def _handle_tools_executed(self, ev):
        """Buffer tool call + result pairs."""
        try:
            now = datetime.now(timezone.utc)
            for call, output in ev.zipped():
                # Tool call entry
                call_content = f"{call.name}({call.arguments})"
                self._event_buffer.append({
                    "timestamp": time.monotonic(),
                    "iso_timestamp": now.isoformat(),
                    "role": "tool",
                    "content": call_content,
                    "event_type": "tool_call",
                })
                self._total_events_processed += 1

                # Tool result entry
                result_str = str(output.output)[:500] if output else ""
                if result_str:
                    self._event_buffer.append({
                        "timestamp": time.monotonic(),
                        "iso_timestamp": now.isoformat(),
                        "role": "tool",
                        "content": f"{call.name} → {result_str}",
                        "event_type": "tool_result",
                    })
                    self._total_events_processed += 1

                if self._debug:
                    ts = now.strftime("%H:%M:%S")
                    logger.debug(
                        f"[COMPACTION:EVENT] Buffered: tool_call [{ts}] "
                        f"\"{call_content[:80]}\" (buf={len(self._event_buffer)})"
                    )
        except Exception as e:
            logger.error(f"[COMPACTION:ERROR] Failed to buffer tool event: {e}")

    # ------------------------------------------------------------------
    # Background compaction loop
    # ------------------------------------------------------------------

    async def _compaction_loop(self):
        """Run compaction on a timer. Never raises — logs all errors."""
        try:
            while self._running:
                await asyncio.sleep(self._interval_seconds)
                if not self._running:
                    break
                try:
                    await self._run_compaction_cycle()
                except Exception:
                    logger.exception("[COMPACTION:ERROR] Compaction cycle failed — skipping")
        except asyncio.CancelledError:
            pass

    async def _run_compaction_cycle(self):
        """Execute one compaction cycle: snapshot buffer, call LLM, update tiers."""

        # Snapshot and clear buffer under lock
        async with self._lock:
            if not self._event_buffer:
                return
            snapshot = list(self._event_buffer)
            self._event_buffer.clear()

            # Buffer overflow guard
            if len(snapshot) > 100:
                logger.warning(
                    f"[COMPACTION:ERROR] Buffer overflow ({len(snapshot)} events) — "
                    f"truncating to last 50"
                )
                snapshot = snapshot[-50:]

            prev_hot = self._hot
            prev_warm = self._warm
            prev_cold = self._cold

        elapsed = time.monotonic() - self._last_compaction
        logger.info(
            f"[COMPACTION:CYCLE] Starting cycle {self._cycle_count + 1} — "
            f"{len(snapshot)} events in buffer, {elapsed:.1f}s since last cycle"
        )

        # Format events into transcript with timestamps
        event_lines = []
        for e in snapshot:
            iso = e["iso_timestamp"]
            ts = iso.split("T")[1][:8] if "T" in iso else "??:??:??"
            event_lines.append(f"[{ts}] ({e['role']}) {e['content']}")
        transcript = "\n".join(event_lines)

        # Calculate session elapsed time
        now = datetime.now(timezone.utc)
        session_elapsed = (now - self._session_start_time).total_seconds() / 60.0

        # Build prompts
        mode = "unknown"
        try:
            mode = self._state.get_mode()
        except Exception:
            pass

        system_prompt = _COMPACTION_SYSTEM_PROMPT.format(mode=mode)

        user_message = (
            f"Current summary:\n"
            f"[HOT]\n{prev_hot or '(empty)'}\n\n"
            f"[WARM]\n{prev_warm or '(empty)'}\n\n"
            f"[COLD]\n{prev_cold or '(empty)'}\n\n"
            f"New events since last cycle ({len(snapshot)} events, "
            f"{elapsed:.0f}s ago → now):\n{transcript}\n\n"
            f"Current time in session: {session_elapsed:.1f} minutes"
        )

        if self._debug:
            truncated = transcript[:500].replace("\n", " | ")
            logger.debug(
                f"[COMPACTION:INPUT] Transcript ({len(snapshot)} events): \"{truncated}\""
            )

        # Call LLM
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.2,
                max_tokens=600,
            )

            content = response.choices[0].message.content or ""
            usage = response.usage

            # Track tokens and cost
            input_tokens = getattr(usage, "prompt_tokens", 0)
            output_tokens = getattr(usage, "completion_tokens", 0)
            self._total_input_tokens += input_tokens
            self._total_output_tokens += output_tokens

        except Exception as e:
            logger.error(f"[COMPACTION:ERROR] API call failed: {e}")
            # Put events back so they aren't lost
            async with self._lock:
                self._event_buffer = snapshot + self._event_buffer
            return

        # Parse response into tiers
        new_hot, new_warm, new_cold = self._parse_tiers(content)

        if new_hot is None:
            # Parse failed — keep previous summary
            logger.warning(
                f"[COMPACTION:ERROR] Failed to parse response — keeping previous summary. "
                f"Raw: {content[:200]}"
            )
            return

        # Update tiers under lock
        async with self._lock:
            self._hot = new_hot
            self._warm = new_warm
            self._cold = new_cold
            self._cycle_count += 1
            self._last_compaction = time.monotonic()

        if self._debug:
            logger.debug(
                f"[COMPACTION:OUTPUT] GPT-4.1-mini response ({output_tokens} tokens):\n"
                f"  [HOT] {self._hot[:200]}\n"
                f"  [WARM] {self._warm[:200]}\n"
                f"  [COLD] {self._cold[:200]}"
            )

        logger.info(
            f"[COMPACTION:CYCLE] Cycle {self._cycle_count} complete — "
            f"hot={len(self._hot)} warm={len(self._warm)} cold={len(self._cold)} chars "
            f"({len(self._hot) + len(self._warm) + len(self._cold)} total)"
        )

        from profiler.collector import SessionProfiler
        SessionProfiler.get_instance().record(
            "compaction", "cycle",
            cycle_number=self._cycle_count,
            events_processed=len(snapshot),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            hot_chars=len(self._hot),
            warm_chars=len(self._warm),
            cold_chars=len(self._cold),
        )

        # Check if cold needs flushing
        cold_words = len(self._cold.split()) if self._cold else 0
        estimated_tokens = int(cold_words * 1.3)
        if estimated_tokens > self._cold_flush_threshold:
            await self._flush_cold_to_memory()

        # Periodic stats
        if self._cycle_count % 5 == 0:
            stats = self.get_stats()
            logger.info(
                f"[COMPACTION:STATS] After {self._cycle_count} cycles: "
                f"total_events={stats['total_events_processed']}, "
                f"hot={len(self._hot)}c/warm={len(self._warm)}c/cold={len(self._cold)}c, "
                f"model_calls={self._cycle_count}, est_cost=${stats['total_cost_usd']:.4f}"
            )

    def _parse_tiers(self, content: str):
        """Parse [HOT]/[WARM]/[COLD] sections from LLM response.

        Returns (hot, warm, cold) strings, or (None, None, None) if parsing fails.
        """
        hot, warm, cold = "", "", ""
        current = None

        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("[HOT]"):
                current = "hot"
                rest = stripped[5:].strip()
                if rest:
                    hot += rest + "\n"
                continue
            elif stripped.startswith("[WARM]"):
                current = "warm"
                rest = stripped[6:].strip()
                if rest:
                    warm += rest + "\n"
                continue
            elif stripped.startswith("[COLD]"):
                current = "cold"
                rest = stripped[6:].strip()
                if rest:
                    cold += rest + "\n"
                continue

            if current == "hot":
                hot += line + "\n"
            elif current == "warm":
                warm += line + "\n"
            elif current == "cold":
                cold += line + "\n"

        hot = hot.strip()
        warm = warm.strip()
        cold = cold.strip()

        # Validate: at least one section should be non-empty
        if not hot and not warm and not cold:
            return None, None, None

        return hot, warm, cold

    # ------------------------------------------------------------------
    # Cold flush to memory.md
    # ------------------------------------------------------------------

    async def _flush_cold_to_memory(self):
        """Flush cold context to memory.md and replace with pointer."""
        if not self._memory_path or not self._cold:
            return

        flush_timestamp = datetime.now(timezone.utc).isoformat()

        try:
            with open(self._memory_path, "a") as f:
                f.write(f"\n## Context flushed at {flush_timestamp}\n\n")
                f.write(self._cold.strip())
                f.write("\n\n---\n\n")

            self._cold_flush_count += 1

            self._cold = (
                f"[Older context flushed to memory.md at {flush_timestamp} — "
                f"{self._cold_flush_count} flush(es) total. "
                f"File: {self._memory_path}]"
            )

            cold_words = len(self._cold.split())
            logger.info(
                f"[COMPACTION:FLUSH] Cold flushed to memory.md "
                f"(flush #{self._cold_flush_count}, threshold={self._cold_flush_threshold} tokens). "
                f"Cold replaced with pointer."
            )
        except Exception as e:
            logger.error(f"[COMPACTION:ERROR] Failed to flush cold to memory.md: {e}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_summary(self) -> str:
        """Return the current pre-built summary (hot + warm + cold).

        Called by prune/truncate methods — must be non-blocking.
        Returns empty string if no compaction has run yet.
        """
        parts = []
        if self._cold:
            parts.append(f"[SESSION CONTEXT]\n{self._cold}")
        if self._warm:
            parts.append(f"[EARLIER CONTEXT]\n{self._warm}")
        if self._hot:
            parts.append(f"[RECENT CONTEXT]\n{self._hot}")
        return "\n\n".join(parts)

    def get_event_buffer_size(self) -> int:
        """Return number of events in the pending buffer."""
        return len(self._event_buffer)

    def get_stats(self) -> Dict[str, Any]:
        """Return compaction stats for monitoring and debug logging."""
        input_cost = (self._total_input_tokens / 1_000_000) * _INPUT_COST_PER_M
        output_cost = (self._total_output_tokens / 1_000_000) * _OUTPUT_COST_PER_M
        age = time.monotonic() - self._last_compaction if self._last_compaction else 0

        return {
            "cycle_count": self._cycle_count,
            "cold_flush_count": self._cold_flush_count,
            "total_events_processed": self._total_events_processed,
            "buffer_size": len(self._event_buffer),
            "hot_length": len(self._hot),
            "warm_length": len(self._warm),
            "cold_length": len(self._cold),
            "last_compaction_age_seconds": round(age, 1),
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "total_cost_usd": round(input_cost + output_cost, 6),
        }

    # ------------------------------------------------------------------
    # Session folder management
    # ------------------------------------------------------------------

    def _init_session_folder(self):
        """Create the per-session log folder with memory.md and session_meta.json."""
        base_dir = os.getenv(
            "COMPACTION_SESSION_LOG_DIR",
            str(Path(__file__).parent.parent / "session_logs"),
        )

        session_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
        self._session_dir = Path(base_dir) / self._user_id / session_timestamp

        try:
            self._session_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(
                f"[COMPACTION:ERROR] Failed to create session folder "
                f"{self._session_dir}: {e} — continuing without persistence"
            )
            self._session_dir = None
            self._memory_path = None
            return

        # Initialize memory.md
        self._memory_path = self._session_dir / "memory.md"
        try:
            now = datetime.now(timezone.utc)
            self._memory_path.write_text(
                f"# Nova Session Memory\n\n"
                f"- **user_id**: {self._user_id}\n"
                f"- **started**: {now.isoformat()}\n"
                f"- **mode**: {self._state.get_mode()}\n\n"
                f"---\n\n"
            )
        except Exception as e:
            logger.error(f"[COMPACTION:ERROR] Failed to write memory.md: {e}")
            self._memory_path = None

        # Write session_meta.json (atomic)
        try:
            meta = {
                "user_id": self._user_id,
                "session_start": datetime.now(timezone.utc).isoformat(),
                "initial_mode": self._state.get_mode(),
                "model": self._model,
                "interval_seconds": self._interval_seconds,
                "cold_flush_threshold": self._cold_flush_threshold,
            }
            meta_path = self._session_dir / "session_meta.json"
            tmp_path = meta_path.with_suffix(".json.tmp")
            tmp_path.write_text(json.dumps(meta, indent=2))
            os.replace(str(tmp_path), str(meta_path))
        except Exception as e:
            logger.error(f"[COMPACTION:ERROR] Failed to write session_meta.json: {e}")

        logger.info(f"[COMPACTION:SESSION] Created session folder: {self._session_dir}")

    def _write_final_metadata(self):
        """Update session_meta.json with final stats on stop()."""
        if not self._session_dir:
            return

        meta_path = self._session_dir / "session_meta.json"
        if not meta_path.exists():
            return

        try:
            meta = json.loads(meta_path.read_text())
            meta.update({
                "session_end": datetime.now(timezone.utc).isoformat(),
                "total_compaction_cycles": self._cycle_count,
                "total_cold_flushes": self._cold_flush_count,
                "total_events_processed": self._total_events_processed,
                "estimated_cost_usd": self.get_stats()["total_cost_usd"],
                "final_mode": self._state.get_mode(),
            })
            tmp_path = meta_path.with_suffix(".json.tmp")
            tmp_path.write_text(json.dumps(meta, indent=2))
            os.replace(str(tmp_path), str(meta_path))
            logger.info(f"[COMPACTION:SESSION] Final metadata saved to {meta_path}")
        except Exception as e:
            logger.error(f"[COMPACTION:ERROR] Failed to write final metadata: {e}")
