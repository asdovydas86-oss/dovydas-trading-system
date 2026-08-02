"""``python -m fmis.pipeline`` — run the CLI without an installed console script.

Kept trivial on purpose: it forwards to `fmis.pipeline.cli.main` and does nothing
else, so the module-execution path and the ``fmits`` console script exercise
exactly the same code.

**The ``__name__`` guard is load-bearing, not boilerplate.** Several suites walk
the package tree and import every module to check export collisions and import
boundaries. Without the guard, that import *runs the CLI*, which parses whatever
`sys.argv` happens to hold — pytest's own arguments — and the failure surfaces as
an argparse error inside an unrelated test. Discovered exactly that way.
"""

from __future__ import annotations

from fmis.pipeline.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
