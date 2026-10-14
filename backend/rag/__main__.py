"""Read-only validation command: python -m backend.rag [--strict]."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from backend.rag.loader import CorpusLoadError, DATA_ROOT, DEFAULT_MANIFEST, load_corpus


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    parser.add_argument("--as-of", type=date.fromisoformat, default=None,
                        help="date for reproducible future-date checks, not a verification date")
    parser.add_argument("--strict", action="store_true", help="exit 1 if any record was rejected")
    args = parser.parse_args(argv)
    try:
        result = load_corpus(args.manifest, data_root=args.data_root, as_of=args.as_of)
    except CorpusLoadError as exc:
        print(json.dumps({"error": str(exc), "complete": False}))
        return 2
    print(json.dumps(asdict(result.report), indent=2, sort_keys=True))
    if not result.report.complete:
        return 2
    return 1 if args.strict and result.report.rejected_records else 0


if __name__ == "__main__":
    raise SystemExit(main())
