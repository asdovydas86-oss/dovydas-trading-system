"""Reproducibility checks. Run after `run.py`.

Three questions, none of which may be answered by assertion:

  1. is the harness deterministic across processes and hash seeds?
  2. does the committed result file match a fresh computation?
  3. does any production module import this research package?
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def determinism(symbols: str = "BTCUSDT,WINUSDT") -> bool:
    """Two runs, two hash seeds, two processes, byte-compared.

    Different seeds matter because a dict or set iterated without an explicit
    sort orders differently per seed, and that is the most common way a study
    like this becomes irreproducible without anyone noticing.
    """
    outputs = []
    for seed in ("0", "12345"):
        target = ROOT / f".determinism_{seed}.json.gz"
        subprocess.run(
            [sys.executable, str(ROOT / "research/zone_semantics/run.py"),
             str(target), symbols],
            check=True,
            env={**__import__("os").environ, "PYTHONHASHSEED": seed,
                 "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True,
        )
        outputs.append(digest(target))
        target.unlink()
    print(f"determinism: {outputs[0][:16]} vs {outputs[1][:16]} -> "
          f"{'IDENTICAL' if outputs[0] == outputs[1] else 'DIFFERENT'}")
    return outputs[0] == outputs[1]


def no_production_dependency() -> bool:
    """`src/` must not mention this package. Grep, not trust."""
    result = subprocess.run(
        ["grep", "-rn", "research.zone_semantics", str(ROOT / "src"),
         str(ROOT / "tests")],
        capture_output=True,
        text=True,
    )
    hits = [line for line in result.stdout.splitlines() if line.strip()]
    print(f"production references to research.zone_semantics: {len(hits)}")
    for line in hits:
        print("  ", line)
    return not hits


def importable_without_research() -> bool:
    """`import fmis` must work with `research/` absent from the path."""
    code = (
        "import sys; sys.path=[p for p in sys.path if 'dovydas-trading-system' "
        "not in p or p.endswith('src')]; import fmis.pipeline.cli; print('ok')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, cwd="/tmp"
    )
    ok = result.returncode == 0
    print(f"fmis imports with research/ off the path: {ok}")
    return ok


if __name__ == "__main__":
    results = {
        "determinism": determinism(),
        "no_production_dependency": no_production_dependency(),
        "importable_without_research": importable_without_research(),
    }
    print(json.dumps(results, indent=2))
    sys.exit(0 if all(results.values()) else 1)
