# Python Code Style

## File Structure
Every `.py` file follows this order:
1. Module docstring (1-5 lines, plain text)
2. `from __future__ import annotations`
3. Stdlib imports
4. Third-party imports (`numpy`, `pydantic`, `scipy`)
5. Relative/local imports
6. Module-level constants (`UPPER_SNAKE_CASE`)
7. Private helpers (`_` prefix)
8. Public functions/classes

## Type Hints
- Always `from __future__ import annotations` as first import
- Use `list[Type]`, `dict[str, Type]`, `Type | None` — NOT `List`, `Dict`, `Optional` from `typing`
- Import `Any`, `Protocol`, `Callable` from `typing` (no builtin equivalent)
- All function parameters and return types must have annotations

## Naming
- Explicit snake_case. Names explain what is going on (`x_coordinate` not `x`)
- No single-letter variables except loop indices (`i`, `j`) or math coordinates (`x`, `y`, `z` in NumPy)
- Domain abbreviations OK: `anthro`, `rom`, `kpts`, `vel`, `cfg`
- Suffixes: `_l`/`_r` (left/right), `_fn` (callable), `_ratio` (dimensionless), `_m` (meters), `_deg` (degrees), `_cm` (centimeters)
- Constants: `UPPER_SNAKE_CASE` at module level. No magic numbers inline.

## Imports
- `import numpy as np` — always aliased
- `import math` — use `math.` prefix, never `from math import *`
- Explicit `from` imports for everything else (`from pathlib import Path`)

## Docstrings
- Module-level: always present, 1-5 lines, plain descriptive text
- Public functions: only if behavior is non-obvious. Plain text, no Args/Returns/Google/reST format.
- Private functions (`_` prefix): no docstrings
- Classes: only if the class name doesn't make the purpose obvious

## Classes
- Pydantic `BaseModel` for data containers and config types
- Plain classes for engines/algorithms — no inheritance unless abstracting 2+ concrete implementations
- Prefer pure functions over stateful classes
- Private methods use `_` prefix; public API is minimal

## Error Handling
- `try/except` only for graceful fallback on expected failures
- `ValueError` for bad config or initialization errors
- No custom exception classes unless you have 3+ distinct error types
- No defensive error handling in core algorithm paths
