"""
Coaching Orchestrator — Priority-based dispatch for real-time coaching cues.

Separates deterministic cached audio cues (faults, rep counts, positive
reinforcement) from LLM-generated speech (motivation, set recaps).
Cached cues always take priority and duck the LLM audio track while playing.
"""

import asyncio
import enum
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# =============================================================================
# CUE DISPLAY LABELS (cue_key → human-readable label for reports)
# =============================================================================

CUE_DISPLAY_LABELS: Dict[str, str] = {
    "knees_out": "Knees out!",
    "chest_up": "Chest up!",
    "deeper": "Go deeper!",
    "heels_down": "Heels down!",
    "even_it_out": "Even it out!",
    "slow_down": "Slow down!",
    "brace_core": "Brace core!",
    "hips_through": "Hips through!",
    "flat_back": "Flat back!",
    "lock_out": "Lock it out!",
    "good_rep": "Good rep!",
    "great_depth": "Great depth!",
    "strong": "Strong!",
    "clean": "Clean!",
    "perfect": "Perfect!",
}


# =============================================================================
# PRIORITY LEVELS
# =============================================================================

class CuePriority(enum.IntEnum):
    """Lower number = higher priority."""
    FAULT_CUE = 1
    REP_COUNT_CUE = 2
    POSITIVE_CUE = 3
    LLM_MOTIVATION = 10
    LLM_SET_RECAP = 20


# =============================================================================
# EVENT DATACLASS
# =============================================================================

@dataclass(order=True)
class CoachingEvent:
    """A coaching event to be dispatched by the orchestrator."""
    priority: int
    timestamp: float = field(compare=False)
    event_type: str = field(compare=False)  # "cached_cue" | "llm_motivation" | "llm_set_recap"
    cue_key: Optional[str] = field(compare=False, default=None)
    data: Dict[str, Any] = field(compare=False, default_factory=dict)


@dataclass
class CueLogEntry:
    """Record of a cue that was actually dispatched (for set reports)."""
    wall_time: float       # time.time() for X-axis plotting
    label: str             # Human-readable ("Knees out!", "Rep 3", "Good rep!")
    category: str          # "fault" | "rep" | "positive" | "motivation"


# =============================================================================
# ORCHESTRATOR
# =============================================================================

class CoachingOrchestrator:
    """
    Owns the priority queue and dispatches coaching cues and LLM calls.

    Cached cues (faults, rep counts, positive reinforcement) play immediately
    on a secondary audio track. LLM calls (motivation, set recaps) only fire
    when the queue is clear and are secondary to cached cues.

    When a cached cue plays, the LLM audio is ducked (paused) so the cue
    is heard clearly, then resumed after playout.
    """

    def __init__(
        self,
        play_cached_audio_fn: Callable,
        generate_llm_reply_fn: Callable,
        duck_llm_fn: Callable,
        unduck_llm_fn: Callable,
        get_cue_audio_fn: Callable,
        advance_set_fn: Optional[Callable] = None,
    ):
        self._play_cached = play_cached_audio_fn
        self._generate_llm = generate_llm_reply_fn
        self._duck_llm = duck_llm_fn
        self._unduck_llm = unduck_llm_fn
        self._get_cue_audio = get_cue_audio_fn
        self._advance_set = advance_set_fn

        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._llm_speaking: bool = False
        self._processing: bool = False
        self._processor_task: Optional[asyncio.Task] = None

        # Per-set tracking for motivation triggers
        self._set_rep_count: int = 0
        self._set_target_reps: Optional[int] = None
        self._set_number: int = 0  # Increments across sets (1-indexed in output)
        self._clean_streak: int = 0
        self._set_clean_count: int = 0
        self._recent_faults: List[str] = []
        self._last_motivation_rep: int = 0
        self._motivation_interval: int = 3
        self._positive_cue_keys: List[str] = []

        # Fault cue rate limiting (orchestrator-level, per cue key)
        self._last_fault_cue_time: float = 0.0
        self._min_fault_cue_gap: float = 8.0  # seconds between fault cues

        # Rest state — suppress rep/fault processing during rest
        self._resting: bool = False
        self._total_sets: Optional[int] = None

        # Set report data collection
        self._set_cue_log: List[CueLogEntry] = []
        self._set_angle_samples: List[Dict[str, Any]] = []
        self._set_rep_events: List[Dict[str, Any]] = []
        self._set_start_wall_time: float = time.time()

        # Deferred report generation — accumulate per-set snapshots,
        # generate all charts at session end (stop())
        self._pending_reports: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        """Start the background queue processor."""
        self._processing = True
        self._processor_task = asyncio.create_task(self._process_loop())
        logger.info("[ORCHESTRATOR] Started")

    def stop(self):
        """Stop the queue processor and generate any pending set reports."""
        self._processing = False
        if self._processor_task:
            self._processor_task.cancel()
            self._processor_task = None
        self._generate_pending_reports()
        logger.info("[ORCHESTRATOR] Stopped")

    def reset_set(
        self,
        target_reps: Optional[int] = None,
        positive_cue_keys: Optional[List[str]] = None,
        total_sets: Optional[int] = None,
    ):
        """Reset per-set tracking state for a new set."""
        if total_sets is not None:
            self._total_sets = total_sets
        self._set_rep_count = 0
        self._set_target_reps = target_reps
        self._clean_streak = 0
        self._set_clean_count = 0
        self._recent_faults = []
        self._last_motivation_rep = 0
        self._positive_cue_keys = list(positive_cue_keys or [])
        self._last_fault_cue_time = 0.0
        self._resting = False
        # Reset report data
        self._set_cue_log = []
        self._set_angle_samples = []
        self._set_rep_events = []
        self._set_start_wall_time = time.time()

    def on_rest_complete(self):
        """Called when rest timer expires — resume rep/fault processing."""
        self._resting = False
        logger.info("[ORCHESTRATOR] Rest complete — resuming")

    # ------------------------------------------------------------------
    # Angle sample recording (called from voice agent on frame_data)
    # ------------------------------------------------------------------

    def record_angle_sample(self, angles_dict: Dict[str, Any]) -> None:
        """Record a joint angle snapshot for set report timeseries."""
        if self._resting or not angles_dict:
            return
        knee_l = angles_dict.get("knee_flexion_l", 0.0)
        knee_r = angles_dict.get("knee_flexion_r", 0.0)
        self._set_angle_samples.append({
            "wall_time": time.time(),
            "avg_knee": (knee_l + knee_r) / 2.0,
            "trunk_flexion": angles_dict.get("trunk_flexion", 0.0),
        })

    # ------------------------------------------------------------------
    # Event enqueueing (called from IPC handler)
    # ------------------------------------------------------------------

    async def on_fault(
        self,
        cue_key: Optional[str],
        fault_type: str,
        severity: str,
        message: str = "",
    ):
        """Enqueue a fault correction cue (HIGHEST priority)."""
        if self._resting:
            return
        self._recent_faults.append(fault_type)
        if len(self._recent_faults) > 10:
            self._recent_faults = self._recent_faults[-10:]

        # Rate limit fault cues to avoid overwhelming the lifter
        now = time.monotonic()
        if now - self._last_fault_cue_time < self._min_fault_cue_gap:
            return

        if cue_key and self._get_cue_audio(cue_key):
            self._last_fault_cue_time = now
            await self._queue.put(CoachingEvent(
                priority=CuePriority.FAULT_CUE,
                timestamp=time.monotonic(),
                event_type="cached_cue",
                cue_key=cue_key,
                data={"fault_type": fault_type, "severity": severity},
            ))
            logger.info(f"[ORCHESTRATOR] ⬆ Enqueued FAULT cue: {cue_key} (type={fault_type}, severity={severity})")
        elif cue_key:
            logger.info(f"[ORCHESTRATOR] Fault cue '{cue_key}' has no cached audio — skipped")
        else:
            logger.info(f"[ORCHESTRATOR] Fault has no cue_key — skipped (type={fault_type})")

    async def on_rep_complete(
        self,
        rep_number: int,
        depth: str,
        is_clean: bool,
        faults: List[str],
    ):
        """Enqueue rep count cue and evaluate motivation trigger."""
        if self._resting:
            return
        self._set_rep_count += 1  # Track relative reps per set (ignores absolute pipeline number)

        # Record rep event for set report
        self._set_rep_events.append({
            "wall_time": time.time(),
            "rep_number": self._set_rep_count,
            "is_clean": is_clean,
            "depth": depth,
        })

        if is_clean:
            self._clean_streak += 1
            self._set_clean_count += 1
        else:
            self._clean_streak = 0

        # Rep count cue (uses per-set rep number)
        rep_cue_key = f"rep_{self._set_rep_count}"
        if self._get_cue_audio(rep_cue_key):
            await self._queue.put(CoachingEvent(
                priority=CuePriority.REP_COUNT_CUE,
                timestamp=time.monotonic(),
                event_type="cached_cue",
                cue_key=rep_cue_key,
            ))
            logger.info(f"[ORCHESTRATOR] ⬆ Enqueued REP COUNT cue: {rep_cue_key}")
        else:
            logger.info(f"[ORCHESTRATOR] No cached audio for rep cue: {rep_cue_key}")

        logger.info(
            f"[ORCHESTRATOR] Rep {self._set_rep_count}/{self._set_target_reps or '?'} complete — "
            f"clean={is_clean}, streak={self._clean_streak}, set_clean={self._set_clean_count}"
        )

        # Check if set is complete based on target rep count
        if (
            self._set_target_reps is not None
            and self._set_rep_count >= self._set_target_reps
        ):
            self._set_number += 1
            set_data = {
                "set_number": self._set_number,
                "total_reps": self._set_rep_count,
                "clean_reps": self._set_clean_count,
                "avg_depth": 0,
                "depth_consistency": 0,
                "fault_summary": {},
                "trigger": "rep_count",
            }
            await self.on_set_complete(set_data)

            if self._advance_set:
                try:
                    new_target_reps = await self._advance_set()
                    self.reset_set(
                        target_reps=new_target_reps,
                        positive_cue_keys=self._positive_cue_keys,
                    )
                    # Enter rest mode — will be cleared by on_rest_complete()
                    self._resting = True
                    logger.info("[ORCHESTRATOR] Entering rest mode")
                except Exception as e:
                    logger.error(f"[ORCHESTRATOR] advance_set_fn failed: {e}")
            return  # Set complete — skip motivation/positive cues

        # Positive reinforcement for clean reps
        if is_clean and self._positive_cue_keys:
            positive_key = random.choice(self._positive_cue_keys)
            if self._get_cue_audio(positive_key):
                await self._queue.put(CoachingEvent(
                    priority=CuePriority.POSITIVE_CUE,
                    timestamp=time.monotonic(),
                    event_type="cached_cue",
                    cue_key=positive_key,
                ))
                logger.info(f"[ORCHESTRATOR] ⬆ Enqueued POSITIVE cue: {positive_key}")

        # Evaluate LLM motivation at "top of rep" (uses per-set rep number)
        if self._should_trigger_motivation(self._set_rep_count):
            context = self._build_motivation_context(self._set_rep_count, depth, is_clean)
            await self._queue.put(CoachingEvent(
                priority=CuePriority.LLM_MOTIVATION,
                timestamp=time.monotonic(),
                event_type="llm_motivation",
                data=context,
            ))
            self._last_motivation_rep = self._set_rep_count
            logger.info(f"[ORCHESTRATOR] Enqueued motivation at rep {self._set_rep_count}")

    async def on_set_complete(self, set_data: dict):
        """Enqueue LLM set recap (lowest priority).

        Snapshots report data into the event so it survives reset_set().
        """
        # Snapshot report data — reset_set() may be called before
        # the queued event is processed
        set_data["_report"] = {
            "angle_samples": list(self._set_angle_samples),
            "cue_log": list(self._set_cue_log),
            "rep_events": list(self._set_rep_events),
            "start_time": self._set_start_wall_time,
        }
        await self._queue.put(CoachingEvent(
            priority=CuePriority.LLM_SET_RECAP,
            timestamp=time.monotonic(),
            event_type="llm_set_recap",
            data=set_data,
        ))
        logger.info(f"[ORCHESTRATOR] Set {set_data.get('set_number', '?')} complete — queued recap")

    # ------------------------------------------------------------------
    # Motivation trigger logic
    # ------------------------------------------------------------------

    def _should_trigger_motivation(self, rep_number: int) -> bool:
        """Deterministic logic for when to trigger LLM motivation."""
        if rep_number <= 1:
            return False
        if rep_number - self._last_motivation_rep < self._motivation_interval:
            return False

        reps_remaining = None
        if self._set_target_reps:
            reps_remaining = self._set_target_reps - rep_number

        # Every N reps
        if rep_number % self._motivation_interval == 0:
            return True
        # Last 2 reps of the set
        if reps_remaining is not None and 0 < reps_remaining <= 2:
            return True
        # After 3+ consecutive clean reps (fire every 3rd clean rep)
        if self._clean_streak >= 3 and self._clean_streak % 3 == 0:
            return True

        return False

    def _build_motivation_context(self, rep_number: int, depth: str, is_clean: bool) -> dict:
        """Build context dict for LLM motivation call."""
        reps_remaining = None
        if self._set_target_reps:
            reps_remaining = self._set_target_reps - rep_number

        return {
            "rep_number": rep_number,
            "reps_remaining": reps_remaining,
            "target_reps": self._set_target_reps,
            "clean_streak": self._clean_streak,
            "recent_faults": list(set(self._recent_faults[-5:])),
            "last_depth": depth,
            "last_clean": is_clean,
        }

    # ------------------------------------------------------------------
    # Queue processing
    # ------------------------------------------------------------------

    async def _process_loop(self):
        """Main dispatch loop — runs continuously while active."""
        while self._processing:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            try:
                await self._dispatch(event)
            except Exception as e:
                logger.error(f"[ORCHESTRATOR] Dispatch error: {e}")

    async def _dispatch(self, event: CoachingEvent):
        """Dispatch a single event based on its type and priority."""
        logger.info(
            f"[ORCHESTRATOR] ▶ Dispatching: type={event.event_type} priority={event.priority} "
            f"cue_key={event.cue_key} age={time.monotonic() - event.timestamp:.1f}s"
        )

        if event.event_type == "cached_cue":
            await self._dispatch_cached_cue(event)

        elif event.event_type == "llm_motivation":
            # Drop stale motivation events (>8s old)
            age = time.monotonic() - event.timestamp
            if age > 1.0:
                logger.info("[ORCHESTRATOR] Dropping stale motivation event (%.1fs old)", age)
                return
            # Drain any pending cached cues first, then speak motivation
            await self._drain_cached_cues()
            logger.info("[ORCHESTRATOR] → Firing LLM motivation")
            await self._speak_llm_motivation(event.data)
            logger.info("[ORCHESTRATOR] ✓ LLM motivation complete")

        elif event.event_type == "llm_set_recap":
            # Drain any remaining cached cues first
            await self._drain_cached_cues()
            logger.info("[ORCHESTRATOR] → Firing LLM set recap")
            await self._speak_llm_set_recap(event.data)
            logger.info("[ORCHESTRATOR] ✓ LLM set recap complete")

    async def _dispatch_cached_cue(self, event: CoachingEvent):
        """Play a cached cue with LLM audio ducking."""
        # Drop stale cached cues — if a cue sat in the queue too long,
        # the coaching moment has passed
        age = time.monotonic() - event.timestamp
        if age > 0.5:
            logger.info("[ORCHESTRATOR] Dropping stale cached cue: %s (%.1fs old)", event.cue_key, age)
            return

        try:
            logger.info(f"[ORCHESTRATOR] → Playing cached cue: {event.cue_key} (ducking LLM)")
            await self._duck_llm()
            await self._play_cached(event.cue_key)
            # Log successfully played cue for set report
            self._log_dispatched_cue(event)
            logger.info(f"[ORCHESTRATOR] ✓ Cached cue played: {event.cue_key}")
        except Exception as e:
            logger.error(f"[ORCHESTRATOR] Cached cue playback failed ({event.cue_key}): {e}")
        finally:
            try:
                await self._unduck_llm()
            except Exception:
                pass

    async def _drain_cached_cues(self):
        """Drain and play any remaining cached cues before an LLM event."""
        while not self._queue.empty():
            try:
                next_event = self._queue.get_nowait()
                if next_event.event_type == "cached_cue":
                    await self._dispatch_cached_cue(next_event)
                else:
                    # Re-enqueue non-cached events
                    await self._queue.put(next_event)
                    break
            except asyncio.QueueEmpty:
                break

    # ------------------------------------------------------------------
    # Cue logging for set reports
    # ------------------------------------------------------------------

    def _log_dispatched_cue(self, event: CoachingEvent) -> None:
        """Log a successfully dispatched cached cue for the set report."""
        cue_key = event.cue_key or ""
        data = event.data or {}

        # Determine category and label
        if data.get("fault_type"):
            category = "fault"
            label = CUE_DISPLAY_LABELS.get(cue_key, cue_key)
        elif cue_key.startswith("rep_"):
            category = "rep"
            label = f"Rep {cue_key.split('_', 1)[1]}"
        else:
            category = "positive"
            label = CUE_DISPLAY_LABELS.get(cue_key, cue_key)

        self._set_cue_log.append(CueLogEntry(
            wall_time=time.time(),
            label=label,
            category=category,
        ))

    # ------------------------------------------------------------------
    # Set report generation
    # ------------------------------------------------------------------

    def _generate_set_report_from_snapshot(self, set_number: int, report: dict) -> None:
        """Generate a set report PNG from snapshotted data."""
        try:
            from services.set_report import generate_set_report
            generate_set_report(
                set_number=set_number,
                angle_samples=report.get("angle_samples", []),
                cue_log=report.get("cue_log", []),
                rep_events=report.get("rep_events", []),
                set_start_time=report.get("start_time", 0.0),
            )
        except Exception as e:
            logger.error(f"[ORCHESTRATOR] Set report generation failed: {e}")

    def _generate_pending_reports(self) -> None:
        """Generate all deferred set reports (called at session end)."""
        if not self._pending_reports:
            return
        logger.info(f"[ORCHESTRATOR] Generating {len(self._pending_reports)} set report(s)...")
        for entry in self._pending_reports:
            self._generate_set_report_from_snapshot(entry["set_number"], entry["report"])
        self._pending_reports.clear()

    # ------------------------------------------------------------------
    # LLM speech helpers
    # ------------------------------------------------------------------

    async def _speak_llm_motivation(self, context: dict):
        """Generate and speak LLM motivation."""
        reps_remaining = context.get("reps_remaining")
        clean_streak = context.get("clean_streak", 0)
        recent_faults = context.get("recent_faults", [])
        rep_number = context.get("rep_number", 0)

        parts = [f"Rep {rep_number} just finished."]
        if reps_remaining is not None and reps_remaining > 0:
            parts.append(f"{reps_remaining} reps to go.")
        if clean_streak >= 3:
            parts.append(f"{clean_streak} clean reps in a row!")
        if recent_faults:
            parts.append(f"Watch for: {', '.join(recent_faults[-2:])}.")

        context_str = " ".join(parts)

        instructions = (
            f"You are in the middle of a set and you are giving your athlete some motivation"
            f"{context_str} "
            f"Give a SHORT (2-5 words MAX) motivational push. "
            
        )

        logger.info(f"[ORCHESTRATOR] LLM motivation instructions: {instructions[:100]}...")
        self._llm_speaking = True
        try:
            await self._generate_llm(instructions)
            # Log motivation for set report
            self._set_cue_log.append(CueLogEntry(
                wall_time=time.time(),
                label="Motivation",
                category="motivation",
            ))
            logger.info("[ORCHESTRATOR] ✓ LLM motivation spoken")
        except Exception as e:
            logger.error(f"[ORCHESTRATOR] LLM motivation failed: {e}", exc_info=True)
        finally:
            self._llm_speaking = False

    async def _speak_llm_set_recap(self, data: dict):
        """Generate and speak comprehensive LLM set recap."""
        total_reps = data.get("total_reps", 0)
        set_num = data.get("set_number", 0)
        clean_reps = data.get("clean_reps", 0)
        avg_depth = data.get("avg_depth", 0)
        depth_consistency = data.get("depth_consistency", 0)
        fault_summary = data.get("fault_summary", {})

        next_set = set_num + 1
        total_sets_str = f" of {self._total_sets}" if self._total_sets else ""
        parts = [f"Set {set_num}{total_sets_str} just finished: {total_reps} reps. Next up is set {next_set}{total_sets_str}."]
        parts.append(f"{clean_reps}/{total_reps} clean reps.")
        if avg_depth:
            parts.append(f"Average depth: {avg_depth}°.")
        if depth_consistency:
            parts.append(f"Depth consistency (stdev): {depth_consistency}°.")
        if fault_summary:
            fault_lines = []
            for fault_type, stats in fault_summary.items():
                count = stats.get("count", 0)
                avg_sev = stats.get("avg_severity", "N/A")
                fault_lines.append(f"{fault_type}: {count}x (avg severity {avg_sev})")
            parts.append(f"Faults: {'; '.join(fault_lines)}.")

        context_str = " ".join(parts)
        print(context_str)

        instructions = (
            f"Your athlete just finished a set. You are giving them feedback on what they just did using the data."
            f"{context_str} "
            f"Give honest feedback (2-4 sentences). "
            f"Highlight what went well. If recurring faults, "
            f"give ONE specific coaching tip for the next set. "
            f"Be encouraging — reference the numbers."
        )

        logger.info(f"[ORCHESTRATOR] LLM set recap instructions: {instructions[:120]}...")
        self._llm_speaking = True
        try:
            await self._generate_llm(instructions)
            logger.info("[ORCHESTRATOR] ✓ LLM set recap spoken")
        except Exception as e:
            logger.error(f"[ORCHESTRATOR] LLM set recap failed: {e}", exc_info=True)
        finally:
            self._llm_speaking = False
            # Stash report data for deferred generation at session end
            report = data.get("_report")
            if report:
                self._pending_reports.append({"set_number": set_num, "report": report})
            # Only reset if not already reset by rep-count trigger
            # (rep-count trigger resets immediately in on_rep_complete)
            if data.get("trigger") != "rep_count":
                self.reset_set(self._set_target_reps, self._positive_cue_keys)
