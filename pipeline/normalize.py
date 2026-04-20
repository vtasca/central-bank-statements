from __future__ import annotations

from datetime import datetime, timezone

VALID_DOC_TYPES = frozenset({
    "statement",
    "minutes",
    "press_conference",
    "account",
    "decision",
    "summary_opinions",
})


def normalize(doc: dict) -> dict:
    """Enforce the unified document schema, raising ValueError on bad input."""
    defaults = {
        "bank_id": "",
        "doc_type": "",
        "meeting_date": "",
        "published_date": "",
        "title": "",
        "source_url": "",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "language": "en",
        "content_type": "html",
        "text": None,
    }
    result = {**defaults, **doc}

    if result["doc_type"] not in VALID_DOC_TYPES:
        raise ValueError(f"Invalid doc_type: {result['doc_type']!r}")

    for field in ("meeting_date", "published_date"):
        result[field] = _coerce_date(result[field])

    return result


def _coerce_date(value: str | None) -> str:
    if not value:
        return ""
    v = str(value).strip()
    # Already ISO: YYYY-MM-DD
    if len(v) == 10 and v[4] == "-" and v[7] == "-":
        return v
    # Compact: YYYYMMDD
    if len(v) == 8 and v.isdigit():
        return f"{v[:4]}-{v[4:6]}-{v[6:]}"
    # 2-digit year compact: YYMMDD (ECB style)
    if len(v) == 6 and v.isdigit():
        return f"20{v[:2]}-{v[2:4]}-{v[4:]}"
    return v
