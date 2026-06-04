# CoachingAgent Implementation Plan

A reusable agent that guides users through iterative form improvement. Receives real-time biomechanics data per-rep, runs the diagnosis engine + rep scoring, and coaches the user via LLM until form is acceptable or max iterations reached.

## Parts (work on independently, in order)

1. **[Part 1: Pipeline Enrichment](part1-pipeline-enrichment.md)** — Buffer bottom-of-rep frame data in the pipeline and send it via IPC with `rep_complete`. No agent code yet.

2. **[Part 2: Service Wiring](part2-service-wiring.md)** — Add callback routing on CoachingService and coaching mode on CoachingOrchestrator so an agent can receive rep events and control orchestrator behavior.

3. **[Part 3: Diagnosis Bridge](part3-diagnosis-bridge.md)** — Add `build_frame_from_ipc()` to `diagnosis/bridge.py` that maps live pipeline data to the format the diagnosis engine expects.

4. **[Part 4: CoachingAgent](part4-coaching-agent.md)** — The agent itself. Inherits BaseNovaAgent, runs the per-rep diagnosis loop, generates LLM coaching cues, handles set summary and handoff.

5. **[Part 5: Integration](part5-integration.md)** — Wire CoachingAgent into WorkoutAgent (function tool), test end-to-end flow, handle edge cases.

## Key Files Reference

| Component | Path |
|---|---|
| Base agent class | `src/agents/shared/base_agent.py` |
| Existing agent example | `src/agents/teaching_agent.py` |
| WorkoutAgent (caller) | `src/agents/workout_agent.py` |
| CoachingService | `src/services/coaching_service.py` |
| CoachingOrchestrator | `src/services/coaching_orchestrator.py` |
| IPC Bridge | `src/biomechanics/coaching/ipc_bridge.py` |
| Pipeline | `src/biomechanics/pipeline.py` |
| Pose process (IPC caller) | `src/pose/pose_estimation_process.py` |
| Diagnosis engine | `src/biomechanics/diagnosis/engine.py` |
| Diagnosis bridge | `src/biomechanics/diagnosis/bridge.py` |
| Rep scoring | `src/biomechanics/diagnosis/rep_scoring.py` |
| Diagnosis types | `src/biomechanics/diagnosis/types.py` |
| Calibration | `src/biomechanics/calibration.py` |
| UserData | `src/agents/shared/userdata.py` |
| Visualizer (gold standard) | `scripts/visualize_video_squats.py` |
