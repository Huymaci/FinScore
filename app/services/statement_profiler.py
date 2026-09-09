"""Infer the layout of an arbitrary bank statement, then *prove* the inference.

Why this module exists
----------------------
`_auto_mapping()` in imports.py matches header strings against a fixed alias
list. That fails on any bank whose wording is not already in the list, on files
with preamble rows above the header, and on files with no usable header at all.
Worse, it has no verification step: when it picks the wrong column it imports
wrong numbers silently, which for financial data is the one failure mode that
must never happen.

The approach here inverts the priority. Instead of asking "which column is
called something like 'amount'?", it asks "which assignment of columns to roles
makes the sheet internally consistent?" — and for most statements there is an
arithmetic answer, not a guess.

The running-balance invariant
-----------------------------
Most bank statements carry a running balance column. If they do, then for every
row i:

    balance[i] - balance[i-1] == signed_amount[i]

A candidate mapping either satisfies that for ~every row or it does not. When it
does, the mapping is *proved* correct: no confidence score, no model, no
training data — arithmetic. That single property is what makes format-agnostic
extraction tractable, and it is why this module is built around scoring
candidates rather than recognising headers.

When there is no balance column the module falls back to weaker but still
deterministic signals (type homogeneity, date monotonicity, debit/credit
exclusivity) and reports a lower confidence, which is the signal for the caller
to ask a human — or, optionally, to consult an LLM whose answer is then run
back through these same checks.

Layering
--------
    L0  grid            typed cells (caller supplies; xlsx already gives types)
    L1  profile         per-column type/format statistics
    L2  candidates      enumerate plausible role assignments
    L3  verify          score against invariants  <-- decides correctness
    L4  fingerprint     cache the winner as a reusable template

Nothing in L0-L4 requires a network call or a model. An LLM, if used at all,
belongs strictly between L2 and L3: it may *propose* a mapping, it may never
*accept* one.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

# ---------------------------------------------------------------------------
# L1 - value parsing
#
# Every parser below decides its convention *per column*, never per cell. A
# single cell is usually ambiguous ("01/02/2026", "1.234"); a column of fifty
# cells almost never is. Committing to one reading for the whole column is what
# turns an ambiguous file into a decidable one.
# ---------------------------------------------------------------------------

DATE_PATTERNS = [
    (re.compile(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})$"), "dmy_or_mdy"),
    (re.compile(r"^(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})$"), "ymd"),
    (re.compile(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2})$"), "dmy_or_mdy_short"),
]
# Excel keeps dates as days since 1899-12-30 in the 1900 system.
EXCEL_EPOCH = date(1899, 12, 30)


def _text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalise_header(value) -> str:
    """Fold a header to ASCII lowercase so Vietnamese diacritics stop mattering."""
    text = unicodedata.normalize("NFD", _text(value).lower())
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = text.replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def detect_number_convention(values: list[str]) -> str:
    """Decide whether a column uses 1.234.567,89 (vn) or 1,234,567.89 (en).

    VND amounts are whole numbers, so a trailing group of exactly three digits
    after the final separator is a thousands group, not a fraction. Deciding
    this once per column avoids the classic bug where "1.234" parses as 1.234
    in one row and 1234 in the next.
    """
    vn_hits = en_hits = 0
    for raw in values:
        text = re.sub(r"[^\d.,\-]", "", raw)
        if not text:
            continue
        last_dot, last_comma = text.rfind("."), text.rfind(",")
        if last_dot == -1 and last_comma == -1:
            continue
        if last_comma > last_dot:
            tail = text[last_comma + 1:]
            vn_hits += 1 if len(tail) != 3 else 0
            en_hits += 1 if len(tail) == 3 else 0
        else:
            tail = text[last_dot + 1:]
            en_hits += 1 if len(tail) != 3 else 0
            vn_hits += 1 if len(tail) == 3 else 0
    return "vn" if vn_hits > en_hits else "en"


def parse_number(raw, convention: str = "en"):
    """Return a float, or None when the cell is not a number."""
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    text = _text(raw)
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    # A reference like "FT12345678" or a description like "GD 001 THANH TOAN"
    # must not survive as a number. Stripping the letters and parsing whatever
    # digits remain is exactly what let a ref_no column outscore the real amount
    # column. Only currency decoration may sit alongside the digits.
    if re.search(r"[A-Za-z]", re.sub(r"(?i)\b(vnd|usd|đ)\b", "", text)):
        return None
    text = re.sub(r"[^\d.,+\-]", "", text)
    if not re.search(r"\d", text):
        return None
    if convention == "vn":
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", "")
    try:
        value = float(text)
    except ValueError:
        return None
    return -value if negative else value


def detect_date_order(values: list[str]) -> str:
    """Resolve dd/mm vs mm/dd for a whole column.

    One cell with a first component above 12 settles it for every other cell in
    the column. Vietnamese statements are dd/mm, so that is the tie-break when
    no cell disambiguates.
    """
    for raw in values:
        text = _text(raw)
        for pattern, kind in DATE_PATTERNS:
            match = pattern.match(text)
            if not match or not kind.startswith("dmy_or_mdy"):
                continue
            first, second = int(match.group(1)), int(match.group(2))
            if first > 12:
                return "dmy"
            if second > 12:
                return "mdy"
    return "dmy"


def parse_date(raw, order: str = "dmy"):
    """Return a datetime, or None. Handles text dates and Excel serials."""
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, date):
        return datetime(raw.year, raw.month, raw.day)
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        # Plausible serial range: 1990-01-01 to 2100-01-01.
        if 32874 <= float(raw) <= 73050:
            return datetime.combine(EXCEL_EPOCH + timedelta(days=int(raw)), datetime.min.time())
        return None
    text = _text(raw)
    if not text:
        return None
    text = text.split()[0]
    for pattern, kind in DATE_PATTERNS:
        match = pattern.match(text)
        if not match:
            continue
        groups = [int(g) for g in match.groups()]
        try:
            if kind == "ymd":
                return datetime(groups[0], groups[1], groups[2])
            year = groups[2] + (2000 if groups[2] < 100 else 0)
            if order == "mdy":
                return datetime(year, groups[0], groups[1])
            return datetime(year, groups[1], groups[0])
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------------------
# L1 - column profiling
# ---------------------------------------------------------------------------

@dataclass
class ColumnProfile:
    index: int
    header: str
    date_ratio: float
    number_ratio: float
    text_ratio: float
    empty_ratio: float
    # Ratios above are over every row; the purities below are over the cells
    # that actually hold a value. A debit column populated on only 20% of rows
    # is still unambiguously numeric, and enumeration must see it that way or
    # the whole debit/credit layout is never even considered.
    number_purity: float
    text_purity: float
    date_purity: float
    populated: int
    distinct_ratio: float
    mean_text_length: float
    number_convention: str
    date_order: str
    all_non_negative: bool
    looks_monotonic_date: bool


def column_uses_date_serials(cells) -> bool:
    """Decide once per column whether bare numbers are Excel date serials.

    A VND amount of 46,083 sits inside the serial range and is indistinguishable
    from 2026-03-05 at the level of a single cell. Two column-level facts break
    the tie: a real date column has *almost every* value in the range, and those
    values land inside a short window, because a statement covers weeks rather
    than decades. An amount column fails both.
    """
    numbers = [parse_number(cell) for cell in cells]
    present = [n for n in numbers if n is not None]
    if len(present) < 3:
        return False
    in_range = [n for n in present if 32874 <= n <= 73050]
    if len(in_range) / len(present) < 0.95:
        return False
    return (max(in_range) - min(in_range)) <= 730


def profile_column(index: int, header: str, cells: list) -> ColumnProfile:
    total = max(len(cells), 1)
    raw = [_text(cell) for cell in cells]
    non_empty = [value for value in raw if value]
    convention = detect_number_convention(non_empty)
    order = detect_date_order(non_empty)

    serials_are_dates = column_uses_date_serials(cells)
    dates = [
        parse_date(cell, order)
        if serials_are_dates or not isinstance(cell, (int, float)) or isinstance(cell, bool)
        else None
        for cell in cells
    ]
    numbers = [parse_number(cell, convention) for cell in cells]
    date_hits = [d for d in dates if d]
    number_hits = [n for n in numbers if n is not None]
    # A cell that parses as a date is not also counted as a number: "2026" would
    # otherwise inflate both ratios and blur the roles.
    number_only = [n for n, d in zip(numbers, dates) if n is not None and d is None]
    text_hits = [v for v, n, d in zip(raw, numbers, dates) if v and n is None and d is None]

    ascending = sum(1 for a, b in zip(date_hits, date_hits[1:]) if b >= a)
    descending = sum(1 for a, b in zip(date_hits, date_hits[1:]) if b <= a)
    span = max(len(date_hits) - 1, 1)

    populated = max(len(non_empty), 1)
    return ColumnProfile(
        index=index,
        header=normalise_header(header),
        date_ratio=len(date_hits) / total,
        number_ratio=len(number_only) / total,
        text_ratio=len(text_hits) / total,
        empty_ratio=1 - len(non_empty) / total,
        number_purity=len(number_only) / populated,
        text_purity=len(text_hits) / populated,
        date_purity=len(date_hits) / populated,
        populated=len(non_empty),
        distinct_ratio=len(set(non_empty)) / max(len(non_empty), 1),
        mean_text_length=sum(len(v) for v in text_hits) / max(len(text_hits), 1),
        number_convention=convention,
        date_order=order,
        all_non_negative=all(n >= 0 for n in number_hits) if number_hits else True,
        looks_monotonic_date=max(ascending, descending) / span > 0.9 if len(date_hits) > 2 else False,
    )


# Real statements carry more letterhead than expected: the MB template used by
# several Vietnamese banks puts its header on row 18, behind a bilingual logo
# block, account details and a two-language notice. A 15-row scan stopped short
# of it and settled on a stray "Loại tiền/Currency" line instead.
DEFAULT_HEADER_SCAN = 40


def find_header_row(grid: list[list], max_scan: int = DEFAULT_HEADER_SCAN) -> int:
    """Return the index of the row that best separates preamble from data.

    Scored by how much more homogeneous the block *below* a row is than the row
    itself: a real header is text where its column is later numeric or dated.
    This is what lets the module skip bank logos, account holder names and
    statement-period lines without knowing they exist.
    """
    best_index, best_score = 0, float("-inf")
    for index in range(min(max_scan, len(grid) - 1)):
        header_row = grid[index]
        body = grid[index + 1: index + 26]
        if not body:
            continue
        width = max((len(r) for r in body), default=0)
        if width < 2:
            continue
        typed = 0
        for column in range(width):
            cells = [row[column] if column < len(row) else None for row in body]
            profile = profile_column(column, "", cells)
            if profile.date_ratio > 0.7 or profile.number_ratio > 0.7 or profile.text_ratio > 0.7:
                typed += 1
        header_is_text = sum(1 for cell in header_row if _text(cell) and parse_number(cell) is None)
        filled = sum(1 for cell in header_row if _text(cell))
        # Reward: consistent columns below, a mostly-textual header, wide rows.
        # The depth penalty breaks ties toward the earlier of two equally good
        # candidates; it must stay small enough that a genuine header 20 rows
        # into a letterhead still outscores a one-cell line near the top.
        score = typed * 2 + header_is_text * 2 + filled - index * 0.25
        if score > best_score:
            best_index, best_score = index, score
    return best_index


# ---------------------------------------------------------------------------
# L2/L3 - candidate mappings and their verification
# ---------------------------------------------------------------------------

ROLE_HINTS = {
    "date": ("ngay", "ngay giao dich", "ngay hieu luc", "trans date", "date", "posting date", "value date", "ngay gd"),
    "description": ("noi dung", "dien giai", "mo ta", "description", "details", "narrative", "remark", "ghi chu"),
    "amount": ("so tien", "amount", "gia tri", "so tien gd"),
    "debit": ("ghi no", "debit", "phat sinh no", "tien ra", "withdrawal", "no"),
    "credit": ("ghi co", "credit", "phat sinh co", "tien vao", "deposit", "co"),
    "balance": ("so du", "balance", "so du cuoi", "running balance", "so du kha dung"),
    "ref_no": ("so tham chieu", "ref", "reference", "so but toan", "ma gd", "transaction id", "so ct"),
}


def header_affinity(profile: ColumnProfile, role: str) -> float:
    """A soft prior from the header text. Never decisive on its own."""
    header = profile.header
    if not header:
        return 0.0
    for hint in ROLE_HINTS[role]:
        if header == hint:
            return 1.0
        if hint in header or header in hint:
            return 0.6
    return 0.0


@dataclass
class Candidate:
    mapping: dict
    score: float = 0.0
    balance_verified: bool = False
    evidence: list[str] = field(default_factory=list)


@dataclass
class InferenceResult:
    mapping: dict
    confidence: float
    balance_verified: bool
    evidence: list[str]
    header_row: int
    profiles: list[ColumnProfile]
    alternatives: list[Candidate]

    @property
    def needs_human_review(self) -> bool:
        """Anything not proved by the balance invariant gets a human or an LLM."""
        return not self.balance_verified and self.confidence < 0.75


def _signed_amounts(body, mapping, profiles):
    """Reconstruct the signed movement per row for a candidate mapping."""
    signed = []
    for row in body:
        def cell(role):
            index = mapping.get(role)
            if index is None or index >= len(row):
                return None
            return row[index]

        if mapping.get("amount") is not None:
            convention = profiles[mapping["amount"]].number_convention
            value = parse_number(cell("amount"), convention)
            signed.append(value)
        else:
            debit_index, credit_index = mapping.get("debit"), mapping.get("credit")
            debit = parse_number(cell("debit"), profiles[debit_index].number_convention) if debit_index is not None else None
            credit = parse_number(cell("credit"), profiles[credit_index].number_convention) if credit_index is not None else None
            if debit and credit:
                signed.append(None)
            elif debit:
                signed.append(-abs(debit))
            elif credit:
                signed.append(abs(credit))
            else:
                signed.append(None)
    return signed


# Banks disagree on two conventions that leave the arithmetic intact but shift
# which pair of rows to compare. Rather than guess, try all four readings and
# keep the one that fits — the invariant itself decides which convention a file
# uses, so no per-bank knowledge is needed here either.
BALANCE_ORIENTATIONS = (
    ("after", False, "balance printed after the transaction"),
    ("before", False, "balance printed before the transaction"),
    ("after", True, "rows ordered newest first"),
    ("before", True, "rows ordered newest first, balance printed before"),
)


def _agreement(balances, signed) -> tuple[int, int]:
    checked = agreed = 0
    for index in range(1, len(balances)):
        previous, current, movement = balances[index - 1], balances[index], signed[index]
        if previous is None or current is None or movement is None:
            continue
        checked += 1
        # Tolerance covers rounding in files that store two decimal places.
        if abs((current - previous) - movement) <= 0.51:
            agreed += 1
    return agreed, checked


def verify_against_balance(body, mapping, profiles) -> tuple[float, str]:
    """The decisive check: does the balance column account for every movement?

    Returns the agreement ratio and a human-readable note. A ratio at or above
    0.95 is treated as proof; the residual allows for the odd fee row that some
    banks fold into the balance without listing separately.
    """
    balance_index = mapping.get("balance")
    if balance_index is None:
        return 0.0, "no balance column"
    convention = profiles[balance_index].number_convention
    raw_balances = [parse_number(row[balance_index] if balance_index < len(row) else None, convention) for row in body]
    raw_signed = _signed_amounts(body, mapping, profiles)

    best = (0.0, "balance column did not reconcile")
    for placement, reverse, label in BALANCE_ORIENTATIONS:
        balances, signed = list(raw_balances), list(raw_signed)
        if reverse:
            balances.reverse()
            signed.reverse()
        if placement == "before":
            # The printed balance excludes the row's own movement, so the gap
            # between rows i-1 and i is explained by row i-1's amount, not
            # row i's. Shifting the movements by one aligns them again.
            signed = [None] + signed[:-1]
        agreed, checked = _agreement(balances, signed)
        if checked < 3:
            continue
        ratio = agreed / checked
        if ratio > best[0]:
            note = f"balance invariant held on {agreed}/{checked} rows"
            if label != BALANCE_ORIENTATIONS[0][2]:
                note += f" ({label})"
            best = (ratio, note)
    if best[0] == 0.0 and all(b is None for b in raw_balances):
        return 0.0, "balance column unreadable"
    return best


def enumerate_candidates(profiles: list[ColumnProfile]) -> list[dict]:
    """Build plausible role assignments rather than committing to one guess."""
    date_columns = [p.index for p in profiles if p.date_purity > 0.8 and p.populated >= 3]
    # A credit column on a salary account may hold a single row all month, so
    # any populated, purely numeric column is a candidate. Enumeration stays
    # cheap (column counts are small) and the invariant discards the noise.
    numeric = [p for p in profiles if p.number_purity > 0.9 and p.populated >= 1]
    numeric_columns = [p.index for p in numeric]
    text_columns = [p for p in profiles if p.text_purity > 0.5 and p.populated >= 3]

    if not date_columns:
        date_columns = [max(profiles, key=lambda p: p.date_ratio).index] if profiles else []
    if not date_columns or not numeric_columns:
        return []

    description = max(text_columns, key=lambda p: p.mean_text_length).index if text_columns else None
    reference = None
    short_text = [p for p in text_columns if p.index != description and p.distinct_ratio > 0.8 and p.mean_text_length < 30]
    if short_text:
        reference = max(short_text, key=lambda p: header_affinity(p, "ref_no")).index

    candidates = []
    for date_column in date_columns[:2]:
        # Layout A: one signed amount column, optional balance.
        for amount_column in numeric_columns:
            for balance_column in [None] + [c for c in numeric_columns if c != amount_column]:
                candidates.append({"date": date_column, "amount": amount_column, "balance": balance_column,
                                   "description": description, "ref_no": reference})
        # Layout B: separate debit and credit columns, optional balance.
        for debit_column in numeric_columns:
            for credit_column in numeric_columns:
                if debit_column == credit_column:
                    continue
                for balance_column in [None] + [c for c in numeric_columns if c not in (debit_column, credit_column)]:
                    candidates.append({"date": date_column, "debit": debit_column, "credit": credit_column,
                                       "balance": balance_column, "description": description, "ref_no": reference})
    return candidates


def score_candidate(body, mapping, profiles) -> Candidate:
    candidate = Candidate(mapping={k: v for k, v in mapping.items() if v is not None})
    evidence, score = [], 0.0

    ratio, note = verify_against_balance(body, candidate.mapping, profiles)
    if ratio >= 0.95:
        candidate.balance_verified = True
        score += 100
        evidence.append(f"PROVED: {note}")
    elif ratio > 0:
        score += ratio * 20
        evidence.append(f"partial: {note}")

    date_profile = profiles[candidate.mapping["date"]]
    if date_profile.looks_monotonic_date:
        score += 8
        evidence.append("date column is monotonic, as a statement should be")
    score += date_profile.date_ratio * 10

    if "debit" in candidate.mapping:
        # In a debit/credit layout exactly one side is populated per row.
        exclusive = 0
        for row in body:
            debit = parse_number(row[candidate.mapping["debit"]] if candidate.mapping["debit"] < len(row) else None)
            credit = parse_number(row[candidate.mapping["credit"]] if candidate.mapping["credit"] < len(row) else None)
            if bool(debit) != bool(credit):
                exclusive += 1
        exclusivity = exclusive / max(len(body), 1)
        score += exclusivity * 25
        if exclusivity > 0.9:
            evidence.append(f"debit/credit mutually exclusive on {exclusivity:.0%} of rows")

    for role in ("date", "amount", "debit", "credit", "balance", "description", "ref_no"):
        index = candidate.mapping.get(role)
        if index is not None:
            affinity = header_affinity(profiles[index], role)
            score += affinity * 6
            if affinity == 1.0:
                evidence.append(f"header of column {index} names the {role} role exactly")

    signed = _signed_amounts(body, candidate.mapping, profiles)
    usable = sum(1 for value in signed if value not in (None, 0))
    score += (usable / max(len(body), 1)) * 15

    # A single amount column that is mostly empty is a debit/credit half being
    # misread as the whole movement; a real signed-amount column is dense.
    if "amount" in candidate.mapping and profiles[candidate.mapping["amount"]].empty_ratio > 0.25:
        score -= 12
        evidence.append("amount column is sparse, which suggests a debit/credit pair")

    candidate.score = score
    candidate.evidence = evidence
    return candidate


def infer_layout(grid: list[list], header_row: int | None = None) -> InferenceResult:
    """Full pipeline: profile, enumerate, verify, rank."""
    if not grid:
        raise ValueError("Sheet is empty")
    if header_row is None:
        header_row = find_header_row(grid)
    headers = grid[header_row] if header_row < len(grid) else []
    body = [row for row in grid[header_row + 1:] if any(_text(cell) for cell in row)]
    if len(body) < 2:
        raise ValueError("Not enough data rows below the detected header")

    width = max(max((len(r) for r in body), default=0), len(headers))
    profiles = [
        profile_column(index, headers[index] if index < len(headers) else "",
                       [row[index] if index < len(row) else None for row in body])
        for index in range(width)
    ]

    scored = sorted((score_candidate(body, mapping, profiles) for mapping in enumerate_candidates(profiles)),
                    key=lambda c: c.score, reverse=True)
    if not scored:
        raise ValueError("No plausible column layout found")

    best = scored[0]
    runner_up = scored[1].score if len(scored) > 1 else 0
    if best.balance_verified:
        confidence = 0.99
    else:
        # Confidence reflects how far the winner is clear of the next candidate,
        # which is the honest question when there is no arithmetic proof.
        margin = (best.score - runner_up) / max(best.score, 1)
        confidence = min(0.74, 0.35 + margin)

    return InferenceResult(
        mapping=best.mapping, confidence=confidence, balance_verified=best.balance_verified,
        evidence=best.evidence, header_row=header_row, profiles=profiles,
        alternatives=scored[1:4],
    )


# ---------------------------------------------------------------------------
# L4 - fingerprinting
# ---------------------------------------------------------------------------

def fingerprint(grid: list[list], header_row: int) -> str:
    """Stable identity for "a file shaped like this one".

    Once a layout is confirmed for a bank, the fingerprint lets every later file
    from that bank reuse the stored mapping outright. Inference — and any LLM
    call — then happens roughly once per bank, not once per upload.
    """
    headers = grid[header_row] if header_row < len(grid) else []
    parts = [normalise_header(cell) for cell in headers if _text(cell)]
    payload = f"{header_row}|{len(parts)}|{'|'.join(parts)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def to_import_mapping(result: InferenceResult) -> dict:
    """Translate an inference into the mapping_json shape imports.py expects."""
    mapping = {"header_rows": result.header_row + 1}
    for role in ("date", "description", "amount", "debit", "credit", "ref_no"):
        if role in result.mapping:
            mapping[role] = result.mapping[role]
    date_index = result.mapping["date"]
    order = result.profiles[date_index].date_order
    mapping["date_formats"] = (["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"] if order == "dmy"
                               else ["%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%d"])
    mapping["number_convention"] = result.profiles[
        result.mapping.get("amount", result.mapping.get("debit", date_index))
    ].number_convention
    return mapping
