"""Gmail SMTP notifier.

Credentials come from env vars (which the workflow wires up from GitHub Secrets):

    GMAIL_USER           - your Gmail address
    GMAIL_APP_PASSWORD   - a 16-char App Password (requires 2FA on the account)
    NOTIFY_TO            - optional; defaults to GMAIL_USER
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

log = logging.getLogger(__name__)


def _format_body(new_jobs: list[dict]) -> str:
    parts: list[str] = []
    # Group by source for a tidier digest.
    by_source: dict[str, list[dict]] = {}
    for j in new_jobs:
        by_source.setdefault(j.get("source", "unknown"), []).append(j)

    for source, jobs in by_source.items():
        parts.append(f"=== {source.upper()} ({len(jobs)}) ===")
        for j in jobs:
            parts.append(
                f"{j.get('title', '(no title)')} @ {j.get('company', '(unknown)')}"
                f" ({j.get('location', '')})\n{j.get('url', '')}"
            )
        parts.append("")
    return "\n\n".join(parts).strip() + "\n"


def send_digest(new_jobs: list[dict]) -> None:
    if not new_jobs:
        log.info("no new jobs; skipping email")
        return

    try:
        user = os.environ["GMAIL_USER"]
        password = os.environ["GMAIL_APP_PASSWORD"]
    except KeyError as missing:
        log.error("missing required env var: %s; skipping email", missing)
        return
    to = os.environ.get("NOTIFY_TO") or user

    msg = EmailMessage()
    msg["Subject"] = f"[job-search] {len(new_jobs)} new posting(s)"
    msg["From"] = user
    msg["To"] = to
    msg.set_content(_format_body(new_jobs))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(user, password)
        server.send_message(msg)
    log.info("sent digest with %d jobs to %s", len(new_jobs), to)
