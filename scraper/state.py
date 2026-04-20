"""Persistent state for already-seen job postings.

State is a dict mapping a stable job id -> ISO-8601 timestamp of first sight.
It is committed back to the repo by the workflow so it survives across runs.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

STATE_PATH = Path(__file__).resolve().parent.parent / "seen_jobs.json"
PRUNE_AFTER_DAYS = 30


def load_state(path: Path = STATE_PATH) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


def save_state(state: dict[str, str], path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.write("\n")


def prune(state: dict[str, str], max_age_days: int = PRUNE_AFTER_DAYS) -> dict[str, str]:
    """Drop entries older than max_age_days so the file doesn't grow forever."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    kept: dict[str, str] = {}
    for job_id, seen_at in state.items():
        try:
            ts = datetime.fromisoformat(seen_at)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except ValueError:
            # Keep malformed entries rather than silently dropping them.
            kept[job_id] = seen_at
            continue
        if ts >= cutoff:
            kept[job_id] = seen_at
    return kept


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
