# tests/

All automated tests for Nowva. Run with:

```bash
PYTHONPATH=src pytest tests/ -x
```

## Structure

Tests mirror the source layout:

| Test file/dir | Tests for |
|---------------|-----------|
| `test_biomechanics/` | Biomechanics engine — faults, rep counting, kinematics, filters, diagnosis |
| `test_coaching_orchestrator.py` | Coaching cue priority queue and event ordering |
| `test_teaching_agent.py` | Teaching mode agent logic |
| `test_audio_cue_service.py` | Pre-cached TTS audio cue service |
| `test_phase2_v5.py`, `test_phase3_v5.py`, `test_phase4_v5.py` | Program generator layers |
| `test_basketball_v5.py` | Program generator sport-specific output |
| `test_program_generator_suite.py` | Full program generator integration suite |

## Conventions

- Framework: **pytest only** (no unittest)
- Float comparison: `pytest.approx(expected, abs=tolerance)`
- Fixtures: JSON data in `test_biomechanics/fixtures/`, shared fixtures in `conftest.py`
- Naming: `test_<what_is_being_tested>` — descriptive, not abbreviated
- Every new public function gets at least one test
