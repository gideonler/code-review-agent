"""
SQLite store for persisting reviews as compliance audit records.
Every review is immutable once written — findings can have their status updated
but the original review record is never deleted or modified.
"""

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from agent.parser import Finding, ReviewResult, Severity, Verdict

DB_PATH = Path(__file__).parent.parent / "audit.db"


def _connect(path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def _db(path: Path = DB_PATH) -> Generator[sqlite3.Connection, None, None]:
    conn = _connect(path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(path: Path = DB_PATH) -> None:
    with _db(path) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS reviews (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at      TEXT NOT NULL,
            target          TEXT NOT NULL,
            git_branch      TEXT,
            git_commit      TEXT,
            git_author      TEXT,
            provider        TEXT NOT NULL,
            model           TEXT,
            smart_mode      INTEGER NOT NULL DEFAULT 0,
            verdict         TEXT,
            summary         TEXT,
            raw             TEXT NOT NULL,
            finding_count   INTEGER NOT NULL DEFAULT 0,
            blocker_count   INTEGER NOT NULL DEFAULT 0,
            reviewer_name   TEXT,
            signed_off_at   TEXT
        );

        -- migrate: add columns if upgrading from older db
        CREATE TABLE IF NOT EXISTS _migrations (name TEXT PRIMARY KEY);


        CREATE TABLE IF NOT EXISTS findings (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            review_id    INTEGER NOT NULL REFERENCES reviews(id),
            severity     TEXT NOT NULL,
            category     TEXT NOT NULL,
            file         TEXT,
            line         TEXT,
            owasp        TEXT,
            cwe          TEXT,
            cve_id       TEXT,
            cvss_score   REAL,
            cvss_severity TEXT,
            cve_description TEXT,
            problem      TEXT,
            impact       TEXT,
            current_code TEXT,
            fix          TEXT,
            status       TEXT NOT NULL DEFAULT 'open',
            status_note  TEXT,
            updated_at   TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_reviews_created ON reviews(created_at);
        CREATE INDEX IF NOT EXISTS idx_findings_review ON findings(review_id);
        CREATE INDEX IF NOT EXISTS idx_findings_status ON findings(status);
        """)
        # Safe migrations for existing databases
        r_cols = [row[1] for row in conn.execute("PRAGMA table_info(reviews)").fetchall()]
        if "reviewer_name" not in r_cols:
            conn.execute("ALTER TABLE reviews ADD COLUMN reviewer_name TEXT")
        if "signed_off_at" not in r_cols:
            conn.execute("ALTER TABLE reviews ADD COLUMN signed_off_at TEXT")

        f_cols = [row[1] for row in conn.execute("PRAGMA table_info(findings)").fetchall()]
        for col, typedef in [
            ("owasp", "TEXT"), ("cwe", "TEXT"), ("cve_id", "TEXT"),
            ("cvss_score", "REAL"), ("cvss_severity", "TEXT"), ("cve_description", "TEXT"),
        ]:
            if col not in f_cols:
                conn.execute(f"ALTER TABLE findings ADD COLUMN {col} {typedef}")


def sign_off(review_id: int, reviewer_name: str, path: Path = DB_PATH) -> None:
    """Stamp a review with the reviewer's name and sign-off timestamp."""
    if not reviewer_name.strip():
        raise ValueError("Reviewer name cannot be empty")
    now = datetime.now(timezone.utc).isoformat()
    with _db(path) as conn:
        conn.execute(
            "UPDATE reviews SET reviewer_name=?, signed_off_at=? WHERE id=?",
            (reviewer_name.strip(), now, review_id),
        )


def save_review(
    result: ReviewResult,
    target: str,
    provider: str,
    smart_mode: bool = False,
    git_branch: str | None = None,
    git_commit: str | None = None,
    git_author: str | None = None,
    model: str | None = None,
    reviewer_name: str | None = None,
    path: Path = DB_PATH,
) -> int:
    """Persists a ReviewResult and returns the new review ID."""
    init_db(path)
    now = datetime.now(timezone.utc).isoformat()

    with _db(path) as conn:
        signed_off_at = now if reviewer_name else None
        cur = conn.execute(
            """INSERT INTO reviews
               (created_at, target, git_branch, git_commit, git_author,
                provider, model, smart_mode, verdict, summary, raw,
                finding_count, blocker_count, reviewer_name, signed_off_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                now, target, git_branch, git_commit, git_author,
                provider, model, int(smart_mode),
                result.verdict.value if result.verdict else None,
                result.summary, result.raw,
                len(result.findings),
                len(result.blockers),
                reviewer_name, signed_off_at,
            ),
        )
        review_id = cur.lastrowid

        for f in result.findings:
            conn.execute(
                """INSERT INTO findings
                   (review_id, severity, category, file, line,
                    owasp, cwe, cve_id, cvss_score, cvss_severity, cve_description,
                    problem, impact, current_code, fix, status)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    review_id, f.severity.value, f.category,
                    f.file, f.line,
                    getattr(f, "owasp", ""), getattr(f, "cwe", ""),
                    getattr(f, "cve_id", ""), getattr(f, "cvss_score", None),
                    getattr(f, "cvss_severity", ""), getattr(f, "cve_description", ""),
                    f.problem, f.impact, f.current_code, f.fix, "open",
                ),
            )

    return review_id


def update_finding_status(finding_id: int, status: str, note: str = "", path: Path = DB_PATH) -> None:
    """
    Update the triage status of a finding.
    status: open | accepted_risk | false_positive | fixed
    """
    allowed = {"open", "accepted_risk", "false_positive", "fixed"}
    if status not in allowed:
        raise ValueError(f"Invalid status '{status}'. Must be one of: {allowed}")

    now = datetime.now(timezone.utc).isoformat()
    with _db(path) as conn:
        conn.execute(
            "UPDATE findings SET status=?, status_note=?, updated_at=? WHERE id=?",
            (status, note, now, finding_id),
        )


def list_reviews(limit: int = 50, path: Path = DB_PATH) -> list[sqlite3.Row]:
    init_db(path)
    with _db(path) as conn:
        return conn.execute(
            """SELECT * FROM reviews ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()


def get_review(review_id: int, path: Path = DB_PATH) -> tuple[sqlite3.Row, list[sqlite3.Row]]:
    with _db(path) as conn:
        review = conn.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone()
        findings = conn.execute(
            "SELECT * FROM findings WHERE review_id=? ORDER BY CASE severity "
            "WHEN 'BLOCKER' THEN 0 WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 "
            "WHEN 'LOW' THEN 3 ELSE 4 END",
            (review_id,),
        ).fetchall()
    return review, findings


def review_stats(path: Path = DB_PATH) -> dict:
    """Aggregate stats for the compliance dashboard."""
    init_db(path)
    with _db(path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
        verdicts = conn.execute(
            "SELECT verdict, COUNT(*) as n FROM reviews GROUP BY verdict"
        ).fetchall()
        open_blockers = conn.execute(
            "SELECT COUNT(*) FROM findings WHERE severity='BLOCKER' AND status='open'"
        ).fetchone()[0]
        by_category = conn.execute(
            "SELECT category, COUNT(*) as n FROM findings GROUP BY category ORDER BY n DESC"
        ).fetchall()
        recent = conn.execute(
            "SELECT created_at, verdict, target, blocker_count FROM reviews "
            "ORDER BY created_at DESC LIMIT 10"
        ).fetchall()

    return {
        "total_reviews": total,
        "verdicts": {row["verdict"]: row["n"] for row in verdicts},
        "open_blockers": open_blockers,
        "by_category": [(row["category"], row["n"]) for row in by_category],
        "recent": [dict(r) for r in recent],
    }
