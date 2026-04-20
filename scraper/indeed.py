"""Indeed job search scraper (best-effort).

Indeed routinely serves Cloudflare challenges to datacenter IPs, so many runs
will come back empty or 403. That's expected -- we log loudly and return [].
LinkedIn is the primary signal; Indeed is a bonus when it works.
"""

from __future__ import annotations

import logging
import re
import time
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

SEARCH_URL = "https://www.indeed.com/jobs"

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
}

REQUEST_TIMEOUT = 20
SLEEP_BETWEEN_REQUESTS = 2.5


def _build_url(keywords: str, location: str) -> str:
    if location == "Remote":
        loc = "Remote"
    else:
        loc = location
    params = {
        "q": keywords,
        "l": loc,
        "fromage": "1",  # posted in the last day
        "sort": "date",
    }
    return f"{SEARCH_URL}?{urlencode(params)}"


def _clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", s).strip() if s else ""


def _parse_cards(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    results: list[dict] = []

    # Primary selector: the mosaic job card wrapper.
    cards = soup.select("div.job_seen_beacon, a.tapItem, li div.cardOutline")
    for card in cards:
        link_el = card.find("a", attrs={"data-jk": True}) or card.find(
            "h2", class_=re.compile(r"jobTitle")
        )
        job_key = None
        if link_el and link_el.get("data-jk"):
            job_key = link_el["data-jk"]
        else:
            anchor = card.find("a", href=re.compile(r"jk=[0-9a-f]+"))
            if anchor:
                m = re.search(r"jk=([0-9a-f]+)", anchor["href"])
                if m:
                    job_key = m.group(1)
        if not job_key:
            continue

        title_el = card.find("h2", class_=re.compile(r"jobTitle"))
        if title_el:
            inner = title_el.find("span")
            title = _clean(inner.get_text() if inner else title_el.get_text())
        else:
            title = ""

        company_el = card.find(attrs={"data-testid": "company-name"}) or card.find(
            "span", class_=re.compile(r"companyName")
        )
        location_el = card.find(attrs={"data-testid": "text-location"}) or card.find(
            "div", class_=re.compile(r"companyLocation")
        )

        results.append(
            {
                "id": f"indeed:{job_key}",
                "source": "indeed",
                "title": title,
                "company": _clean(company_el.get_text() if company_el else ""),
                "location": _clean(location_el.get_text() if location_el else ""),
                "url": f"https://www.indeed.com/viewjob?jk={job_key}",
            }
        )
    return results


def search(keywords: str, location: str, max_results: int = 25) -> list[dict]:
    url = _build_url(keywords, location)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as e:
        log.warning("indeed request failed for %r/%r: %s", keywords, location, e)
        return []

    if resp.status_code in (403, 429):
        log.warning(
            "indeed blocked (HTTP %s) for %r/%r", resp.status_code, keywords, location
        )
        return []
    if resp.status_code >= 400:
        log.warning(
            "indeed returned HTTP %s for %r/%r", resp.status_code, keywords, location
        )
        return []

    if "cf-chl" in resp.text or "Cloudflare" in resp.text[:2000]:
        log.warning("indeed served a cloudflare challenge for %r/%r", keywords, location)
        return []

    jobs = _parse_cards(resp.text)
    if not jobs:
        log.info("indeed: 0 cards parsed for %r/%r (HTTP %s, %d bytes)",
                 keywords, location, resp.status_code, len(resp.text))
    else:
        log.info("indeed: %d jobs for %r/%r", len(jobs), keywords, location)

    time.sleep(SLEEP_BETWEEN_REQUESTS)
    return jobs[:max_results]
