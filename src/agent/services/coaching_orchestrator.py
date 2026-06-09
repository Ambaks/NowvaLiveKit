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
import statistics
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
    LLM_MOTIVATION = 2
    LLM_SET_RECAP = 3
    LLM_EXERCISE_RECAP = 4
    POSITIVE_CUE = 6
    FAULT_CUE = 7  # testing: demoted to lowest priority


# =============================================================================
# EVENT DATACLASS
# =============================================================================

@dataclass(order=True)
class CoachingEvent:
    """A coaching event to be dispatched by the orchestrator."""
    priority: int
    timestamp: float = field(compare=False)
    event_type: str = field(compare=False)  # "cached_cue" | "llm_motivation" | "llm_set_recap" | "llm_exercise_recap"
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
        on_workout_complete_fn: Optional[Callable] = None,
        prune_context_fn: Optional[Callable] = None,
    ):
        self._play_cached = play_cached_audio_fn
        self._generate_llm = generate_llm_reply_fn
        self._duck_llm = duck_llm_fn
        self._unduck_llm = unduck_llm_fn
        self._get_cue_audio = get_cue_audio_fn
        self._advance_set = advance_set_fn
        self._on_workout_complete = on_workout_complete_fn
        self._prune_context = prune_context_fn

        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
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
        self._rest_seconds: int = 120
        self._total_sets: Optional[int] = None

        # Set report data collection
        self._set_cue_log: List[CueLogEntry] = []
        self._set_angle_samples: List[Dict[str, Any]] = []
        self._set_rep_events: List[Dict[str, Any]] = []
        self._set_start_wall_time: float = time.time()

        # Deferred report generation — accumulate per-set snapshots,
        # generate all charts at session end (stop())
        self._pending_reports: List[Dict[str, Any]] = []

        # Accumulated per-set summaries for exercise recap
        self._all_set_summaries: List[Dict[str, Any]] = []

        # Diagnosis data — populated by set_diagnosis_data(), consumed by recaps
        self._pending_diagnosis: Optional[Dict[str, Any]] = None
        self._pending_scoring: Optional[Dict[str, Any]] = None
        self._diagnosis_event: asyncio.Event = asyncio.Event()

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
            # Avoid cancelling ourselves when stop() is called from within a
            # callback running inside the processor task.  Setting _processing
            # to False is enough — the loop will exit on its own.
            current = asyncio.current_task()
            if self._processor_task is not current:
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

    def set_diagnosis_data(self, diagnosis: Dict[str, Any], scoring: Dict[str, Any]) -> None:
        """Store diagnosis results from the pipeline and signal any waiting recap."""
        self._pending_diagnosis = diagnosis
        self._pending_scoring = scoring
        self._diagnosis_event.set()
        logger.info(
            f"[ORCHESTRATOR] Diagnosis data received: "
            f"confidence={diagnosis.get('confidence', 0):.2f} "
            f"score={scoring.get('mean_score', 0):.3f}"
        )

    def _consume_diagnosis(self) -> tuple:
        """Return diagnosis data if already available, otherwise skip."""
        diagnosis = self._pending_diagnosis
        scoring = self._pending_scoring
        self._pending_diagnosis = None
        self._pending_scoring = None
        self._diagnosis_event = asyncio.Event()
        return diagnosis, scoring

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
        max_depth_angle: float = 0.0,
        rep_duration_ms: int = 0,
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
            "max_depth_angle": max_depth_angle,
            "rep_duration_ms": rep_duration_ms,
            "faults": faults,
        })

        if is_clean:
            self._clean_streak += 1
            self._set_clean_count += 1
        else:
            self._clean_streak = 0

        # Rep count cue — fire-and-forget on separate audio track
        # (bypasses queue since rep sounds play on a dedicated track)
        rep_cue_key = f"rep_{self._set_rep_count}"
        if self._get_cue_audio(rep_cue_key):
            asyncio.create_task(self._play_cached(rep_cue_key))
            # Log for set report
            self._set_cue_log.append(CueLogEntry(
                wall_time=time.time(),
                label=f"Rep {self._set_rep_count}",
                category="rep",
            ))
            logger.info(f"[ORCHESTRATOR] → Fire-and-forget REP COUNT cue: {rep_cue_key}")
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
            set_data = self._build_set_summary()
            set_data["trigger"] = "rep_count"

            is_last_set = (
                self._total_sets is not None
                and self._set_number >= self._total_sets
            )

            if is_last_set:
                # Last set — snapshot report data and advance session
                set_data["_report"] = {
                    "angle_samples": list(self._set_angle_samples),
                    "cue_log": list(self._set_cue_log),
                    "rep_events": list(self._set_rep_events),
                    "start_time": self._set_start_wall_time,
                }
                if self._advance_set:
                    try:
                        await self._advance_set()
                    except Exception as e:
                        logger.error(f"[ORCHESTRATOR] advance_set_fn failed: {e}")
                # Queue exercise recap instead of set recap
                await self._queue_exercise_recap(set_data)
            else:
                # Mid-workout set complete — normal flow
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
        if is_clean and self._positive_cue_keys and random.random() < 0.3:
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
        """Enqueue LLM set recap.

        Snapshots report data into the event so it survives reset_set().
        Flushes stale in-set events (faults, motivation) before queuing
        so the recap dispatches immediately.
        """
        self._flush_queue()
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

    async def _queue_exercise_recap(self, final_set_data: dict):
        """Queue the exercise recap after the last set completes."""
        self._flush_queue()
        # Add the final set's summary to the accumulated list
        self._all_set_summaries.append({
            "set_number": final_set_data.get("set_number", 0),
            "total_reps": final_set_data.get("total_reps", 0),
            "clean_reps": final_set_data.get("clean_reps", 0),
            "avg_depth": final_set_data.get("avg_depth", 0),
            "depth_consistency": final_set_data.get("depth_consistency", 0),
            "avg_duration_ms": final_set_data.get("avg_duration_ms", 0),
            "fault_summary": final_set_data.get("fault_summary", {}),
        })

        # Stash report data for the final set
        report = final_set_data.get("_report")
        if report:
            self._pending_reports.append({
                "set_number": final_set_data.get("set_number", 0),
                "report": report,
            })

        await self._queue.put(CoachingEvent(
            priority=CuePriority.LLM_EXERCISE_RECAP,
            timestamp=time.monotonic(),
            event_type="llm_exercise_recap",
            data={
                "all_set_summaries": list(self._all_set_summaries),
                "total_sets": self._total_sets,
            },
        ))
        logger.info("[ORCHESTRATOR] Last set complete — queued exercise recap")

    # ------------------------------------------------------------------
    # Set summary computation
    # ------------------------------------------------------------------

    def _build_set_summary(self) -> dict:
        """Compute set stats from accumulated per-rep data."""
        depths = [
            r["max_depth_angle"] for r in self._set_rep_events
            if r.get("max_depth_angle", 0) > 0
        ]
        avg_depth = round(statistics.mean(depths), 1) if depths else 0
        depth_consistency = round(statistics.stdev(depths), 1) if len(depths) > 1 else 0

        durations = [
            r["rep_duration_ms"] for r in self._set_rep_events
            if r.get("rep_duration_ms", 0) > 0
        ]
        avg_duration_ms = round(statistics.mean(durations)) if durations else 0

        # Aggregate faults across all reps
        fault_counts: Dict[str, int] = {}
        for rep in self._set_rep_events:
            for ft in rep.get("faults", []):
                fault_counts[ft] = fault_counts.get(ft, 0) + 1
        fault_summary = {
            ft: {"count": cnt, "pct": round(cnt / len(self._set_rep_events) * 100)}
            for ft, cnt in fault_counts.items()
        } if self._set_rep_events else {}

        return {
            "set_number": self._set_number,
            "total_reps": self._set_rep_count,
            "clean_reps": self._set_clean_count,
            "avg_depth": avg_depth,
            "depth_consistency": depth_consistency,
            "avg_duration_ms": avg_duration_ms,
            "fault_summary": fault_summary,
            "per_rep": [
                {
                    "rep": r["rep_number"],
                    "depth": r["depth"],
                    "depth_angle": round(r.get("max_depth_angle", 0), 1),
                    "clean": r["is_clean"],
                    "faults": r.get("faults", []),
                    "duration_ms": r.get("rep_duration_ms", 0),
                }
                for r in self._set_rep_events
            ],
        }

    # ------------------------------------------------------------------
    # Motivation trigger logic
    # ------------------------------------------------------------------

    def _should_trigger_motivation(self, rep_number: int) -> bool:
        """Fire LLM motivation at the midpoint of the set."""
        if not self._set_target_reps or self._set_target_reps <= 3:
            return False
        midpoint = self._set_target_reps // 2
        return rep_number == midpoint

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
        age_s = time.monotonic() - event.timestamp
        logger.info(
            f"[ORCHESTRATOR] ▶ Dispatching: type={event.event_type} priority={event.priority} "
            f"cue_key={event.cue_key} age={age_s:.1f}s"
        )

        from profiler.collector import SessionProfiler
        SessionProfiler.get_instance().record(
            "coaching", "cue_dispatched",
            cue_key=event.cue_key or "",
            cue_event_type=event.event_type,
            priority=int(event.priority),
            queue_age_ms=round(age_s * 1000, 1),
        )

        if event.event_type == "cached_cue":
            await self._dispatch_cached_cue(event)

        elif event.event_type == "llm_motivation":
            # Drop stale motivation events
            age = time.monotonic() - event.timestamp
            if age > 1.5:
                logger.info("[ORCHESTRATOR] Dropping stale motivation event (%.1fs old)", age)
                return
            # Drain any pending cached cues first, then speak motivation
            await self._drain_cached_cues()
            logger.info("[ORCHESTRATOR] → Firing LLM motivation")
            await self._speak_llm_motivation(event.data)
            logger.info("[ORCHESTRATOR] ✓ LLM motivation complete")

        elif event.event_type == "llm_set_recap":
            logger.info("[ORCHESTRATOR] → Firing LLM set recap")
            await self._speak_llm_set_recap(event.data)
            logger.info("[ORCHESTRATOR] ✓ LLM set recap complete")

        elif event.event_type == "llm_exercise_recap":
            logger.info("[ORCHESTRATOR] → Firing LLM exercise recap")
            await self._speak_llm_exercise_recap(event.data)
            logger.info("[ORCHESTRATOR] ✓ LLM exercise recap complete")

    async def _dispatch_cached_cue(self, event: CoachingEvent):
        """Play a cached cue with LLM audio ducking."""
        # Drop stale cached cues — if a cue sat in the queue too long,
        # the coaching moment has passed
        age = time.monotonic() - event.timestamp
        if age > 1.0:
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

    def _flush_queue(self):
        """Drop all pending events — called at set boundaries to clear stale cues."""
        dropped = 0
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                dropped += 1
            except asyncio.QueueEmpty:
                break
        if dropped:
            logger.info(f"[ORCHESTRATOR] Flushed {dropped} stale events at set boundary")

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
            from agent.services.set_report import generate_set_report
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
        if clean_streak >= 2:
            parts.append(f"{clean_streak} clean reps in a row!")
        if recent_faults:
            parts.append(f"Recent Faults: {', '.join(recent_faults[-2:])}.")

        context_str = " ".join(parts)

        instructions = (
            f"You are in the middle of a set and you are giving your athlete some motivation you have about one and a half seconds to say something."
            f"Give a SHORT (2-5 words MAX) motivational push. "
            f"Here is the data:"
            f"{context_str} "
            
        )

        logger.info(f"[ORCHESTRATOR] LLM motivation instructions: {instructions[:100]}...")
        try:
            handle = await self._generate_llm(instructions)
            # Log motivation for set report
            self._set_cue_log.append(CueLogEntry(
                wall_time=time.time(),
                label="Motivation",
                category="motivation",
            ))
            logger.info("[ORCHESTRATOR] ✓ LLM motivation spoken")
        except Exception as e:
            logger.error(f"[ORCHESTRATOR] LLM motivation failed: {e}", exc_info=True)

    async def _speak_llm_set_recap(self, data: dict):
        """Generate and speak comprehensive LLM set recap."""
        diagnosis, scoring = self._consume_diagnosis()

        set_num = data.get("set_number", 0)
        total_reps = data.get("total_reps", 0)
        clean_reps = data.get("clean_reps", 0)
        avg_depth = data.get("avg_depth", 0)
        depth_consistency = data.get("depth_consistency", 0)
        avg_duration_ms = data.get("avg_duration_ms", 0)
        fault_summary = data.get("fault_summary", {})
        per_rep = data.get("per_rep", [])

        next_set = set_num + 1
        total_sets_str = f" of {self._total_sets}" if self._total_sets else ""

        # Build structured context for LLM
        parts = [
            f"Set {set_num}{total_sets_str} just finished: {total_reps} reps.",
            f"Next up is set {next_set}{total_sets_str}.",
            f"{clean_reps}/{total_reps} clean reps.",
        ]
        if avg_depth:
            parts.append(f"Average depth: {avg_depth}° (consistency stdev: {depth_consistency}°).")
        if avg_duration_ms:
            parts.append(f"Average rep tempo: {avg_duration_ms}ms.")
        if fault_summary:
            fault_lines = []
            for fault_type, stats in fault_summary.items():
                count = stats.get("count", 0)
                pct = stats.get("pct", 0)
                fault_lines.append(f"{fault_type}: {count}/{total_reps} reps ({pct}%)")
            parts.append(f"Faults: {'; '.join(fault_lines)}.")
        if per_rep:
            rep_lines = []
            for r in per_rep:
                faults_str = f" faults={r['faults']}" if r.get("faults") else ""
                rep_lines.append(
                    f"  Rep {r['rep']}: {r['depth']} ({r['depth_angle']}°) "
                    f"{'clean' if r['clean'] else 'fault'}{faults_str}"
                )
            parts.append("Per-rep breakdown:\n" + "\n".join(rep_lines))

        # Enrich with diagnosis data if available
        if diagnosis and scoring:
            parts.extend(self._build_diagnosis_context(diagnosis, scoring))

        context_str = " ".join(parts)

        if diagnosis and scoring:
            instructions = (
                f"Your athlete just finished a set. Here's their biomechanics analysis and rep data. "
                f"Give honest, encouraging feedback (2-3 sentences). "
                f"Lead with the form score, give the ONE specific adjustment from the analysis, "
                f"end on what went well. You have {self._rest_seconds - 5} seconds. "
                f"Here is the data: "
                f"{context_str}"
            )
        else:
            instructions = (
                f"Your athlete just finished a set. You are giving them feedback on what they just did using the data. "
                f"Give honest feedback. You have {self._rest_seconds - 5} seconds to make your point. "
                f"Highlight what went well. If recurring faults, "
                f"give ONE specific coaching tip for the next set. "
                f"Be encouraging — reference the numbers. "
                f"Here is the data: "
                f"{context_str}"
            )

        logger.info(f"[ORCHESTRATOR] LLM set recap instructions: {instructions[:120]}...")
        try:
            handle = await self._generate_llm(instructions)
            logger.info("[ORCHESTRATOR] ✓ LLM set recap spoken")
            # Prune old conversation items to prevent progressive latency
            if self._prune_context:
                try:
                    await self._prune_context(max_items=6)
                except Exception as e:
                    logger.warning(f"[ORCHESTRATOR] Post-recap context prune failed: {e}")
        except Exception as e:
            logger.error(f"[ORCHESTRATOR] LLM set recap failed: {e}", exc_info=True)
        finally:
            # Report stashing runs always (data integrity)
            report = data.get("_report")
            if report:
                self._pending_reports.append({"set_number": set_num, "report": report})
            # Accumulate set summary for exercise recap
            summary: Dict[str, Any] = {
                "set_number": set_num,
                "total_reps": total_reps,
                "clean_reps": clean_reps,
                "avg_depth": avg_depth,
                "depth_consistency": depth_consistency,
                "avg_duration_ms": avg_duration_ms,
                "fault_summary": fault_summary,
            }
            if diagnosis and scoring:
                summary["diagnosis"] = diagnosis
                summary["scoring"] = scoring
            self._all_set_summaries.append(summary)
            # Only reset if not already reset by rep-count trigger
            # (rep-count trigger resets immediately in on_rep_complete)
            if data.get("trigger") != "rep_count":
                self.reset_set(self._set_target_reps, self._positive_cue_keys)

    @staticmethod
    def _build_diagnosis_context(diagnosis: dict, scoring: dict) -> List[str]:
        """Build diagnosis-enriched context lines for the LLM prompt."""
        parts: List[str] = []

        mean_pct = round(scoring.get("mean_score", 0) * 100)
        dims = scoring.get("per_dimension", {})
        dim_labels = [
            ("depth", "depth"), ("trunk", "trunk_control"),
            ("knee", "knee_tracking"), ("symmetry", "symmetry"),
            ("ankle", "ankle"),
        ]
        dim_str = ", ".join(
            f"{label}: {round(dims[key] * 100)}"
            for label, key in dim_labels if key in dims
        )
        parts.append(f"\nFORM SCORE: {mean_pct}/100 ({dim_str})")

        slope = scoring.get("trend_slope", 0)
        if slope > 0.01:
            trend = "improving"
        elif slope < -0.01:
            trend = "declining"
        else:
            trend = "stable"
        parts.append(f"TREND: {trend} over the set")

        immediate = diagnosis.get("immediate_causes", [])
        if immediate:
            top = immediate[0]
            parts.append(f"TOP ISSUE: {top.get('explanation', 'N/A')}")
            delta = top.get("parameter_delta")
            if delta:
                delta_str = ", ".join(f"{k}: {v}" for k, v in delta.items())
                parts.append(f"ADJUSTMENT: {delta_str}")

        session_causes = diagnosis.get("session_causes", [])
        if session_causes:
            parts.append(f"SESSION PATTERN: {session_causes[0].get('explanation', '')}")

        confidence = diagnosis.get("confidence", 0)
        parts.append(f"Analysis confidence: {round(confidence * 100)}%")

        return parts

    async def _speak_llm_exercise_recap(self, data: dict):
        """Generate and speak comprehensive exercise recap after all sets."""
        # Consume pending diagnosis for the final set
        diagnosis, scoring = self._consume_diagnosis()

        all_summaries = data.get("all_set_summaries", [])
        total_sets = data.get("total_sets", len(all_summaries))

        # Attach final set's diagnosis if available
        if diagnosis and scoring and all_summaries:
            all_summaries[-1]["diagnosis"] = diagnosis
            all_summaries[-1]["scoring"] = scoring

        # Compute aggregate stats
        total_reps = sum(s.get("total_reps", 0) for s in all_summaries)
        total_clean = sum(s.get("clean_reps", 0) for s in all_summaries)
        clean_pct = round(total_clean / total_reps * 100) if total_reps > 0 else 0

        # Aggregate depth across sets
        all_depths = [s.get("avg_depth", 0) for s in all_summaries if s.get("avg_depth")]
        overall_avg_depth = round(statistics.mean(all_depths), 1) if all_depths else 0

        # Aggregate tempo across sets
        all_tempos = [s.get("avg_duration_ms", 0) for s in all_summaries if s.get("avg_duration_ms")]
        overall_avg_tempo = round(statistics.mean(all_tempos)) if all_tempos else 0

        # Aggregate faults across all sets
        all_faults: Dict[str, int] = {}
        for s in all_summaries:
            for fault_type, stats in s.get("fault_summary", {}).items():
                all_faults[fault_type] = all_faults.get(fault_type, 0) + stats.get("count", 0)

        # Per-set breakdown
        per_set_lines = []
        for s in all_summaries:
            sn = s.get("set_number", 0)
            tr = s.get("total_reps", 0)
            cr = s.get("clean_reps", 0)
            ad = s.get("avg_depth", 0)
            depth_str = f", avg depth {ad}°" if ad else ""
            faults_in_set = s.get("fault_summary", {})
            fault_str = ""
            if faults_in_set:
                fault_parts = [f"{ft}: {st['count']}x" for ft, st in faults_in_set.items()]
                fault_str = f", faults: {'; '.join(fault_parts)}"
            per_set_lines.append(f"Set {sn}: {tr} reps, {cr} clean{depth_str}{fault_str}")

        parts = [
            f"Exercise complete! {total_sets} sets finished.",
            f"Total: {total_reps} reps, {total_clean} clean ({clean_pct}%).",
        ]
        if overall_avg_depth:
            parts.append(f"Overall average depth: {overall_avg_depth}°.")
        if overall_avg_tempo:
            parts.append(f"Overall average tempo: {overall_avg_tempo}ms per rep.")
        if per_set_lines:
            parts.append(f"Per-set breakdown: {'; '.join(per_set_lines)}.")
        if all_faults:
            top_faults = sorted(all_faults.items(), key=lambda x: x[1], reverse=True)[:3]
            fault_str = ", ".join(f"{ft}: {cnt}x across all sets" for ft, cnt in top_faults)
            parts.append(f"Most common faults: {fault_str}.")

        # Diagnosis progression across sets
        diagnosed_sets = [s for s in all_summaries if "scoring" in s]
        has_diagnosis = len(diagnosed_sets) > 0
        if diagnosed_sets:
            score_lines = []
            for s in diagnosed_sets:
                sn = s["set_number"]
                mean_pct = round(s["scoring"].get("mean_score", 0) * 100)
                score_lines.append(f"Set {sn}: {mean_pct}/100")
            parts.append(f"Form score progression: {'; '.join(score_lines)}.")

            if len(diagnosed_sets) >= 2:
                first_score = diagnosed_sets[0]["scoring"].get("mean_score", 0)
                last_score = diagnosed_sets[-1]["scoring"].get("mean_score", 0)
                delta = round((last_score - first_score) * 100)
                if delta > 0:
                    parts.append(f"Overall: improved by {delta} points from first to last set.")
                elif delta < 0:
                    parts.append(f"Overall: declined by {abs(delta)} points from first to last set.")

            all_issues = []
            for s in diagnosed_sets:
                diag = s.get("diagnosis", {})
                immediate = diag.get("immediate_causes", [])
                if immediate:
                    all_issues.append(f"Set {s['set_number']}: {immediate[0].get('explanation', '')}")
            if all_issues:
                parts.append(f"Key issues by set: {'; '.join(all_issues)}.")

        context_str = " ".join(parts)

        if has_diagnosis:
            instructions = (
                f"Your athlete just finished their entire exercise. Here's their comprehensive biomechanics analysis. "
                f"{context_str} "
                f"Give honest, encouraging feedback (3-5 sentences). "
                f"Reference the form score progression, highlight the specific improvement or issue, "
                f"and give one key takeaway for next session. "
                f"End on a high note — they just finished!"
            )
        else:
            instructions = (
                f"Your athlete just finished their entire exercise. Give them a comprehensive recap. "
                f"{context_str} "
                f"Give honest, encouraging feedback (3-5 sentences). "
                f"Highlight overall performance, progression across sets, and one key takeaway. "
                f"End on a high note — they just finished!"
            )

        logger.info(f"[ORCHESTRATOR] LLM exercise recap instructions: {instructions[:120]}...")
        try:
            handle = await self._generate_llm(instructions)
            logger.info("[ORCHESTRATOR] ✓ LLM exercise recap spoken")
            # Only fire workout_complete AFTER speech has played out
            if self._on_workout_complete:
                try:
                    await self._on_workout_complete()
                except Exception as e:
                    logger.error(f"[ORCHESTRATOR] on_workout_complete callback failed: {e}")
        except Exception as e:
            logger.error(f"[ORCHESTRATOR] LLM exercise recap failed: {e}", exc_info=True)
