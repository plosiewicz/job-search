"""Entrypoint: scrape boards, dedupe against seen-state, email new postings."""

from __future__ import annotations

import logging
import sys

from . import indeed, linkedin, notify, state

TITLES = [
    "Data Scientist",
    "Machine Learning Engineer",
    "Solutions Architect",
    "Sales Engineer",
    "Forward Deployed Engineer",
]

LOCATIONS = ["San Francisco Bay Area", "Remote"]

BOARDS = [
    ("linkedin", linkedin.search),
    ("indeed", indeed.search),
]


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )


def collect() -> list[dict]:
    """Query every (board, title, location) combo and return a deduped list."""
    seen_ids: set[str] = set()
    all_jobs: list[dict] = []
    for board_name, search_fn in BOARDS:
        for title in TITLES:
            for location in LOCATIONS:
                try:
                    jobs = search_fn(title, location)
                except Exception as e:  # noqa: BLE001 -- never let one board kill the run
                    logging.exception("%s search failed for %r/%r: %s",
                                      board_name, title, location, e)
                    continue
                for job in jobs:
                    if job["id"] in seen_ids:
                        continue
                    seen_ids.add(job["id"])
                    all_jobs.append(job)
    return all_jobs


def filter_new(jobs: list[dict], seen: dict[str, str]) -> list[dict]:
    return [j for j in jobs if j["id"] not in seen]


def main() -> int:
    configure_logging()
    seen = state.prune(state.load_state())
    found = collect()
    logging.info("collected %d unique postings across boards", len(found))

    new_jobs = filter_new(found, seen)
    logging.info("%d of those are new since last run", len(new_jobs))

    if new_jobs:
        try:
            notify.send_digest(new_jobs)
        except Exception as e:  # noqa: BLE001
            logging.exception("email send failed; will not record ids as seen: %s", e)
            # Persist unchanged so we retry next run.
            state.save_state(seen)
            return 1

    now = state.now_iso()
    for job in new_jobs:
        seen[job["id"]] = now
    state.save_state(seen)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
