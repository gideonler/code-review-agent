"""
Parses structured findings from the LLM's review text into typed objects
so the Streamlit UI can render them with badges, filters, and sorting.
"""

import re
from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    BLOCKER = "BLOCKER"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class Verdict(str, Enum):
    APPROVE = "APPROVE"
    APPROVE_WITH_NOTES = "APPROVE WITH MINOR NOTES"
    REQUEST_CHANGES = "REQUEST CHANGES"
    BLOCK = "BLOCK"


SEVERITY_ORDER = {
    Severity.BLOCKER: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}

SEVERITY_COLORS = {
    Severity.BLOCKER: "#FF4B4B",
    Severity.HIGH: "#FF8C00",
    Severity.MEDIUM: "#FFC107",
    Severity.LOW: "#4CAF50",
    Severity.INFO: "#2196F3",
}

VERDICT_COLORS = {
    Verdict.APPROVE: "#4CAF50",
    Verdict.APPROVE_WITH_NOTES: "#8BC34A",
    Verdict.REQUEST_CHANGES: "#FF8C00",
    Verdict.BLOCK: "#FF4B4B",
}


@dataclass
class Finding:
    severity: Severity
    category: str
    file: str
    line: str
    problem: str
    impact: str
    fix: str
    current_code: str = ""
    owasp: str = ""
    cwe: str = ""
    # Populated by enricher.py after NVD lookup
    cve_id: str = ""
    cvss_score: float | None = None
    cvss_severity: str = ""
    cve_description: str = ""
    raw: str = ""


@dataclass
class ReviewResult:
    summary: str = ""
    findings: list[Finding] = field(default_factory=list)
    positive_notes: str = ""
    verdict: Verdict | None = None
    raw: str = ""

    @property
    def blockers(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.BLOCKER]

    @property
    def findings_by_severity(self) -> list[Finding]:
        return sorted(self.findings, key=lambda f: SEVERITY_ORDER.get(f.severity, 99))


# Matches: [BLOCKER] [SECURITY] — File: foo.py, Line: 42
_FINDING_HEADER = re.compile(
    r"\[(?P<severity>BLOCKER|HIGH|MEDIUM|LOW|INFO)\]\s*"
    r"\[(?P<category>[A-Z_]+)\]\s*[—\-]+\s*"
    r"(?:File:\s*(?P<file>[^\n,]+?))?"
    r"(?:[,\s]*Line:\s*(?P<line>[^\n]+))?",
    re.IGNORECASE,
)

_FIELD_RE = re.compile(
    r"(?:Problem|Impact|Fix):\s*(?P<value>.+?)(?=\n(?:Problem|Impact|Fix|$)|\Z)",
    re.DOTALL | re.IGNORECASE,
)


def _extract_field(text: str, label: str) -> str:
    m = re.search(
        rf"{label}:\s*(.+?)(?=\n(?:OWASP|CWE|Problem|Impact|Current code|Fix|\[|POSITIVE|VERDICT)|$)",
        text, re.DOTALL | re.IGNORECASE,
    )
    return m.group(1).strip() if m else ""


def _extract_inline_field(text: str, label: str) -> str:
    """Extracts a single-line field like 'OWASP: A03: Injection'."""
    m = re.search(rf"^{label}:\s*(.+)$", text, re.MULTILINE | re.IGNORECASE)
    if not m:
        return ""
    val = m.group(1).strip()
    return "" if val.upper() in ("N/A", "NA", "NONE", "-") else val


def _extract_code_block(text: str, label: str) -> str:
    """Extracts content inside a fenced code block after a label like 'Current code:' or 'Fix:'."""
    m = re.search(
        rf"{label}:\s*```[\w]*\n(.*?)```",
        text, re.DOTALL | re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()
    # Fallback: plain text after label if no code fence
    return _extract_field(text, label)


def parse_review(raw_text: str) -> ReviewResult:
    result = ReviewResult(raw=raw_text)

    # --- SUMMARY ---
    summary_m = re.search(r"SUMMARY\s*\n+(.*?)(?=\nFINDINGS|\Z)", raw_text, re.DOTALL | re.IGNORECASE)
    if summary_m:
        result.summary = summary_m.group(1).strip()

    # --- FINDINGS ---
    findings_m = re.search(r"FINDINGS\s*\n+(.*?)(?=\nPOSITIVE NOTES|\nVERDICT|\Z)", raw_text, re.DOTALL | re.IGNORECASE)
    if findings_m:
        findings_block = findings_m.group(1)
        # Split on each finding header
        parts = re.split(r"(?=\[(?:BLOCKER|HIGH|MEDIUM|LOW|INFO)\])", findings_block, flags=re.IGNORECASE)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            header_m = _FINDING_HEADER.match(part)
            if not header_m:
                continue
            try:
                severity = Severity(header_m.group("severity").upper())
            except ValueError:
                continue

            result.findings.append(Finding(
                severity=severity,
                category=header_m.group("category") or "",
                file=(header_m.group("file") or "").strip(),
                line=(header_m.group("line") or "").strip(),
                owasp=_extract_inline_field(part, "OWASP"),
                cwe=_extract_inline_field(part, "CWE"),
                problem=_extract_field(part, "Problem"),
                impact=_extract_field(part, "Impact"),
                current_code=_extract_code_block(part, "Current code"),
                fix=_extract_code_block(part, "Fix"),
                raw=part,
            ))

    # --- POSITIVE NOTES ---
    positive_m = re.search(r"POSITIVE NOTES\s*\n+(.*?)(?=\nVERDICT|\Z)", raw_text, re.DOTALL | re.IGNORECASE)
    if positive_m:
        result.positive_notes = positive_m.group(1).strip()

    # --- VERDICT ---
    verdict_m = re.search(r"VERDICT\s*[:\n]+\s*(APPROVE WITH MINOR NOTES|APPROVE|REQUEST CHANGES|BLOCK)", raw_text, re.IGNORECASE)
    if verdict_m:
        verdict_str = verdict_m.group(1).upper()
        try:
            result.verdict = Verdict(verdict_str)
        except ValueError:
            result.verdict = None

    return result
