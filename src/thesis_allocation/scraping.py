"""Researcher profile enrichment with explicit per-row status reporting."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.request import Request, urlopen

import pandas as pd

from thesis_allocation.schema import clean_text, normalize_researchers


USER_AGENT = (
    "computational-thesis-allocation/0.1 "
    "(research administration; respectful automated retrieval)"
)


class VisibleTextParser(HTMLParser):
    """Extract visible text while excluding scripts, styles, and metadata."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._body_depth = 0
        self._saw_body = False
        self._all_text: list[str] = []
        self._body_text: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs
        lowered = tag.casefold()
        if lowered in {"script", "style", "noscript", "template", "svg"}:
            self._skip_depth += 1
        if lowered == "body":
            self._saw_body = True
            self._body_depth += 1

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.casefold()
        if lowered in {"script", "style", "noscript", "template", "svg"}:
            self._skip_depth = max(0, self._skip_depth - 1)
        if lowered == "body":
            self._body_depth = max(0, self._body_depth - 1)

    def handle_data(self, data: str) -> None:
        if self._skip_depth or not data.strip():
            return
        self._all_text.append(data)
        if self._body_depth:
            self._body_text.append(data)

    def text(self) -> str:
        values = self._body_text if self._saw_body else self._all_text
        return " ".join(" ".join(values).split())


@dataclass(frozen=True)
class ScrapeResult:
    """Enriched researcher table and non-fatal retrieval warnings."""

    researchers: pd.DataFrame
    warnings: tuple[str, ...] = ()


def extract_visible_text(html: str) -> str:
    """Extract normalized visible text from an HTML document."""

    parser = VisibleTextParser()
    parser.feed(html)
    parser.close()
    return parser.text()


def clean_profile_text(text: object) -> str:
    """Remove known KU Leuven navigation and publication-list boilerplate."""

    cleaned = " ".join(clean_text(text).split())
    header = (
        "KU Leuven Home CITIP Home About Board Members Staff Members "
        "Education Research Publications CiTiP Conferences Contact Home "
        "Staff members Staff Members"
    )
    cleaned = cleaned.replace(header, " ")

    contact = re.search(r"\bcontact\b", cleaned[:600], flags=re.IGNORECASE)
    if contact:
        cleaned = cleaned[contact.end() :]

    publication_markers = (
        r"\bPublications\s+query=user:",
        r"\bPublications\s+Type\b",
        r"\bPublications\s+Projects=user\b",
    )
    for marker in publication_markers:
        match = re.search(marker, cleaned, flags=re.IGNORECASE)
        if match:
            cleaned = cleaned[: match.start()]
    return " ".join(cleaned.split())


def derive_publications_url(profile_url: object) -> str:
    """Derive the KU Leuven Lirias CV URL used by the legacy scripts."""

    match = re.search(r"/staff/(\d+)/?$", clean_text(profile_url))
    if not match:
        return ""
    numeric_id = match.group(1)
    if numeric_id.startswith("0"):
        numeric_id = numeric_id[1:]
    return f"https://lirias.kuleuven.be/cv?Username=u{numeric_id}"


def download_html(url: str, *, timeout: float = 20.0) -> str:
    """Download one UTF-8-compatible HTML page."""

    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310
        payload = response.read()
        encoding = response.headers.get_content_charset() or "utf-8"
    return payload.decode(encoding, errors="replace")


def enrich_researchers(
    researchers: pd.DataFrame,
    *,
    refresh: bool = False,
    timeout: float = 20.0,
    delay_seconds: float = 0.5,
    fetcher: Callable[..., str] = download_html,
) -> ScrapeResult:
    """Fetch missing profile and publication text without dropping failed rows."""

    result = normalize_researchers(researchers)
    result["profile_scrape_status"] = ""
    result["publications_scrape_status"] = ""
    warnings: list[str] = []

    for index, row in result.iterrows():
        email = row["email"]
        profile_url = clean_text(row["profile_url"])
        should_fetch_profile = refresh or not clean_text(row["profile_description"])
        if not should_fetch_profile:
            result.at[index, "profile_scrape_status"] = "existing"
        elif not profile_url:
            result.at[index, "profile_scrape_status"] = "no_url"
            warnings.append(f"{email}: no profile URL")
        else:
            try:
                html = fetcher(profile_url, timeout=timeout)
                profile_text = clean_profile_text(extract_visible_text(html))
                result.at[index, "profile_description"] = profile_text
                result.at[index, "profile_scrape_status"] = "ok"
            except Exception as exc:  # Per-row failures belong in the output.
                status = f"error:{type(exc).__name__}"
                result.at[index, "profile_scrape_status"] = status
                warnings.append(f"{email}: profile retrieval failed ({exc})")
            if delay_seconds > 0:
                time.sleep(delay_seconds)

        publications_url = clean_text(row["publications_url"]) or derive_publications_url(
            profile_url
        )
        result.at[index, "publications_url"] = publications_url
        should_fetch_publications = refresh or not clean_text(row["publication_list"])
        if not should_fetch_publications:
            result.at[index, "publications_scrape_status"] = "existing"
        elif not publications_url:
            result.at[index, "publications_scrape_status"] = "no_url"
            warnings.append(f"{email}: no publications URL could be derived")
        else:
            try:
                html = fetcher(publications_url, timeout=timeout)
                publication_text = extract_visible_text(html)
                result.at[index, "publication_list"] = publication_text
                result.at[index, "publications_scrape_status"] = "ok"
            except Exception as exc:  # Per-row failures belong in the output.
                status = f"error:{type(exc).__name__}"
                result.at[index, "publications_scrape_status"] = status
                warnings.append(f"{email}: publication retrieval failed ({exc})")
            if delay_seconds > 0:
                time.sleep(delay_seconds)

    return ScrapeResult(
        researchers=result,
        warnings=tuple(dict.fromkeys(warnings)),
    )
