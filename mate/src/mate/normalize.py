"""Normalise values in German and English text so answers can be graded without a judge.

Value questions (prices, dates, durations, identifiers) are graded by finding the value in
the answer: "47.950 €", "EUR 47,950.00" and "47950 euros" are the same amount; "18. Januar
2027", "18 January 2027" and "2027-01-18" are the same date. A judge is kept for summaries
and explanations only (design document, decision F-3).
"""

from __future__ import annotations

import re
from datetime import date

_MONTHS = {
    # English
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9,
    "oct": 10, "nov": 11, "dec": 12,
    # German
    "januar": 1, "jänner": 1, "februar": 2, "märz": 3, "maerz": 3, "mai": 5, "juni": 6,
    "juli": 7, "oktober": 10, "dezember": 12, "okt": 10, "dez": 12,
}
_UNITS = {
    "week": "week", "weeks": "week", "woche": "week", "wochen": "week", "wk": "week", "wks": "week",
    "day": "day", "days": "day", "tag": "day", "tage": "day", "tagen": "day",
    "month": "month", "months": "month", "monat": "month", "monate": "month", "monaten": "month",
    "year": "year", "years": "year", "jahr": "year", "jahre": "year", "jahren": "year",
    "bar": "bar", "m": "m", "meter": "m", "metre": "m", "metres": "m", "meters": "m",
    "kg": "kg", "kw": "kw", "%": "%", "prozent": "%", "percent": "%",
}
_CURRENCY = r"(?:€|eur(?:o|os)?\b|usd|\$)"

_NUM = r"\d{1,3}(?:[.,   ]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?"
_RE_MONEY = re.compile(rf"(?:{_CURRENCY}\s*({_NUM}))|(?:({_NUM})\s*{_CURRENCY})", re.I)
_RE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_RE_DMY_DOTS = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")
_RE_D_MONTH_Y = re.compile(r"\b(\d{1,2})\.?\s+([A-Za-zÄÖÜäöü]+)\.?\s+(\d{4})\b")
_RE_MONTH_D_Y = re.compile(r"\b([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})\b")
_RE_QTY = re.compile(rf"({_NUM})\s*(%|[A-Za-zäöü]+)\b", re.I)
_RE_ID = re.compile(r"\b[A-Z]{1,5}-?\d[\w-]*\b")


def parse_number(s: str) -> float | None:
    """A number written with either convention: '47.950,00', '47,950.00', '47 950', '9'."""
    s = s.replace(" ", " ").replace(" ", " ").strip()
    s = s.replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:
        # The last separator is the decimal one.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    else:
        # One kind of separator. Followed by exactly three digits it groups thousands
        # ("47.950", "47,950", "1.234.567"); otherwise it is the decimal mark ("1,5", "2.75").
        # "1.250" is therefore read as 1250: the generator never plants three-decimal values.
        sep = "," if "," in s else "." if "." in s else ""
        if sep:
            groups = s.split(sep)
            if len(groups) > 2 or (len(groups[-1]) == 3 and groups[0] not in ("", "0")):
                s = s.replace(sep, "")
            else:
                s = s.replace(sep, ".")
    try:
        return float(s)
    except ValueError:
        return None


def _fmt(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".")


def extract_values(text: str) -> set[str]:
    """Every value the text contains, in a canonical form: 'money:47950', 'date:2027-01-18', ..."""
    out: set[str] = set()
    t = text.replace(" ", " ")
    for m in _RE_MONEY.finditer(t):
        n = parse_number(m.group(1) or m.group(2))
        if n is not None:
            out.add(f"money:{_fmt(n)}")
    for m in _RE_ISO.finditer(t):
        _add_date(out, int(m.group(1)), int(m.group(2)), int(m.group(3)))
    for m in _RE_DMY_DOTS.finditer(t):
        _add_date(out, int(m.group(3)), int(m.group(2)), int(m.group(1)))
    for m in _RE_D_MONTH_Y.finditer(t):
        month = _MONTHS.get(m.group(2).lower())
        if month:
            _add_date(out, int(m.group(3)), month, int(m.group(1)))
    for m in _RE_MONTH_D_Y.finditer(t):
        month = _MONTHS.get(m.group(1).lower())
        if month:
            _add_date(out, int(m.group(3)), month, int(m.group(2)))
    for m in _RE_QTY.finditer(t):
        unit = _UNITS.get(m.group(2).lower())
        n = parse_number(m.group(1))
        if unit and n is not None:
            out.add(f"qty:{_fmt(n)} {unit}")
    for m in _RE_ID.finditer(t):
        out.add(f"id:{m.group(0).upper().replace('-', '')}")
    return out


def _add_date(out: set[str], y: int, mth: int, d: int) -> None:
    try:
        out.add(f"date:{date(y, mth, d).isoformat()}")
    except ValueError:
        pass


def canonical(value: str) -> set[str]:
    """The canonical forms of one accepted or superseded value string.

    A value string that contains no recognisable typed value is matched as normalised text.
    """
    found = extract_values(value)
    return found or {f"text:{' '.join(value.lower().split())}"}


def contains_value(answer: str, value: str) -> bool:
    forms = canonical(value)
    if any(f.startswith("text:") for f in forms):
        needle = next(iter(forms))[5:]
        # Whole words only: a count of "2" must not match inside "2027".
        pattern = rf"(?<![\w.,]){re.escape(needle)}(?![\w]|[.,]\d)"
        return re.search(pattern, " ".join(answer.lower().split())) is not None
    return bool(forms & extract_values(answer))
