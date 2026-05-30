# Testing Rules

## Framework
- pytest only. No unittest.
- Run tests: `pytest tests/ -x` (stop on first failure)
- Run specific: `pytest tests/test_biomechanics/test_faults.py -x`

## Test Organization
- Group related tests in classes: `class TestFeatureName:`
- File naming: `test_<module_name>.py`
- Mirror source structure: `src/biomechanics/utils/standing_gate.py` → `tests/test_biomechanics/test_standing_gate.py`

## Fixtures
- JSON fixture data lives in `tests/<test_dir>/fixtures/`
- Shared fixtures go in `conftest.py` at the appropriate directory level
- Use `@pytest.fixture` with return type annotations
- Fixture names describe what they provide (`sample_skeleton_2d`, not `data`)

## Test Helpers
- Private helpers (`_make_skeleton`, `_standing_skeleton`) go at module top, before test classes
- Prefix with `_` — they are not tests
- Helpers that build test objects should accept overrides via parameters

## Numerical Assertions
- Use `pytest.approx(expected, abs=tolerance)` for float comparisons
- Define tolerance constants at module level or in `conftest.py`
- Never use bare `==` for float comparison

## Test Naming
- `test_<what_is_being_tested>` — descriptive, not abbreviated
- Good: `test_bent_knees_fails`, `test_consecutive_resets_on_failure`
- Bad: `test_1`, `test_gate`, `test_basic`

## Coverage
- Every new public function gets at least one test
- Bug fixes: write a failing test first, then fix
- Refactors: verify existing tests pass before and after
