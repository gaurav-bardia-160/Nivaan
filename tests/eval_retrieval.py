"""CLI compatibility wrapper for the reviewed public-API quality evaluation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from test_answer_quality_eval import run_evaluation


if __name__ == "__main__":
    print(json.dumps(run_evaluation(), indent=2))
