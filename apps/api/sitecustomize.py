from __future__ import annotations

import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]

EXTRA_PATHS = [
    HERE / "src",
    REPO_ROOT / "packages" / "checklist" / "python",
    REPO_ROOT / "packages" / "schemas" / "python",
    REPO_ROOT / "packages" / "eval" / "python",
]

for path in EXTRA_PATHS:
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)
