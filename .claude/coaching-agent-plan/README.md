# Diagnosis Pipeline → Voice Agent Integration Plan

Wire the diagnosis engine (HypothesisEngine + rep scoring) into the live pipeline so that structured form analysis results are sent to the voice agent at the end of each set. The diagnosis runs on the pipeline side — where the keypoints and angles already live — and the voice agent receives a single structured summary per set, no raw data.

## Architecture

```
Pipeline side (pose_estimation_process)              Voice agent side
─────────────────────────────────────────            ──────────────────────
Rep completes                                        
  → bottom_kpts + bottom_angles captured             
  → build_frame_from_live_pipeline()                 
  → build_rep_kinematic_summary()                    
  → buffer RepKinematicSummary                       
  → (existing: send rep_complete IPC) ──────────────→ orchestrator plays rep cue
                                                     
Set ends (timeout / target reps / early stop)        
  → build SetFeatures from buffer                    
  → HypothesisEngine.diagnose()                      
  → score_set()                                      
  → (existing: send set_complete IPC) ──────────────→ orchestrator queues set recap
  → send diagnosis_complete IPC ────────────────────→ orchestrator enriches recap
                                                       with diagnosis data
                                                     → LLM speaks data-driven recap
```

## Parts (work in order)

1. **[Part 1: Pipeline Enrichment](part1-pipeline-enrichment.md)** — Buffer bottom-of-rep frame data in the pipeline and send it via IPC with `rep_complete`. *(done)*

2. **[Part 2: Live Pipeline Diagnosis Bridge](part2-service-wiring.md)** — Add key-mapping function in `bridge.py` to convert live pipeline data format (`JointAngles.as_dict()` + `Skeleton3D`) to the frame format the diagnosis engine expects.

3. **[Part 3: SessionTracker Diagnosis Integration](part3-diagnosis-bridge.md)** — Buffer `RepKinematicSummary` per rep in `SessionTracker`, run diagnosis engine + scoring at set end, send `diagnosis_complete` IPC message via new `IPCBridge` method.

4. **[Part 4: Voice Agent Diagnosis Handler](part4-coaching-agent.md)** — Handle `diagnosis_complete` in `CoachingService`, store on orchestrator, enrich the existing set recap LLM prompt with tiered causes, scores, and specific adjustments.

5. **[Part 5: Integration](part5-integration.md)** — Wire athlete params from calibration to `SessionTracker`, end-to-end testing, edge cases.

## Key design decisions

- **Diagnosis runs on the pipeline side**, not the voice agent. Keeps keypoints and heavy computation where the data already lives.
- **No new agent type.** The existing orchestrator + LLM set recap flow is enriched with diagnosis data, not replaced.
- **One message per set.** The voice agent receives `diagnosis_complete` once at set end — no per-rep diagnosis messages.
- **Graceful degradation.** If calibration hasn't happened (no athlete params), diagnosis is skipped and the existing basic set recap continues working.
- **Backward compatible.** All existing IPC messages (`rep_complete`, `set_complete`, `fault`, etc.) continue unchanged.

## Key Files Reference

| Component | Path |
|---|---|
| Pipeline main loop | `src/pose/pose_estimation_process.py` |
| Biomechanics pipeline | `src/biomechanics/pipeline.py` |
| Session tracker | `src/biomechanics/coaching/session_tracker.py` |
| IPC bridge | `src/biomechanics/coaching/ipc_bridge.py` |
| Diagnosis engine | `src/biomechanics/diagnosis/engine.py` |
| Diagnosis bridge | `src/biomechanics/diagnosis/bridge.py` |
| Rep scoring | `src/biomechanics/diagnosis/rep_scoring.py` |
| Diagnosis types | `src/biomechanics/diagnosis/types.py` |
| CoachingService | `src/services/coaching_service.py` |
| CoachingOrchestrator | `src/services/coaching_orchestrator.py` |
| Calibration | `src/biomechanics/calibration.py` |
