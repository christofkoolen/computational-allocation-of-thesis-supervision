"""Language normalization and compatibility helpers."""

from __future__ import annotations

import re
from collections.abc import Iterable

import pandas as pd


LANGUAGE_ALIASES = {
    "de": "German",
    "deu": "German",
    "dut": "Dutch",
    "dutch": "Dutch",
    "en": "English",
    "eng": "English",
    "english": "English",
    "fr": "French",
    "fra": "French",
    "french": "French",
    "ger": "German",
    "german": "German",
    "nl": "Dutch",
    "nld": "Dutch",
}


def canonical_language(value: object) -> str:
    """Return a stable display label for one language value."""

    text = str(value).strip()
    if not text:
        return ""
    return LANGUAGE_ALIASES.get(text.casefold(), text.title())


def parse_languages(value: object) -> tuple[str, ...]:
    """Parse a comma, semicolon, slash, or pipe separated language list."""

    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ()
    if isinstance(value, Iterable) and not isinstance(value, str):
        raw_values = [str(item) for item in value]
    else:
        raw_values = re.split(r"[,;/|]", str(value))

    result: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        language = canonical_language(raw)
        key = language.casefold()
        if language and key not in seen:
            seen.add(key)
            result.append(language)
    return tuple(result)


def first_compatible_language(
    requested: object,
    allowed: object,
) -> tuple[bool, str | None]:
    """Return compatibility and the first compatible requested language.

    An empty list on either side means that no language restriction was supplied.
    """

    requested_languages = parse_languages(requested)
    allowed_languages = parse_languages(allowed)
    if not requested_languages or not allowed_languages:
        return True, requested_languages[0] if requested_languages else None

    allowed_keys = {language.casefold() for language in allowed_languages}
    for language in requested_languages:
        if language.casefold() in allowed_keys:
            return True, language
    return False, None

