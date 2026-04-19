"""
Enriches security findings with live CVE data from the NVD (NIST).
Queries the free NVD REST API v2 — no key required, but rate-limited to
5 requests/30s. Set NVD_API_KEY in .env for 50 requests/30s.

API docs: https://nvd.nist.gov/developers/vulnerabilities
"""

import os
import re
import time
import urllib.request
import urllib.parse
import json
from dataclasses import dataclass

NVD_API_BASE = "https://services.nvd.nist.gov/rest/json/cves/2.0"
_last_request_time: float = 0.0


@dataclass
class CVEResult:
    cve_id: str
    description: str
    cvss_score: float | None
    cvss_severity: str
    url: str


def _rate_limit():
    """Enforce NVD's 5 req/30s limit without an API key."""
    global _last_request_time
    api_key = os.environ.get("NVD_API_KEY")
    min_interval = 0.6 if api_key else 6.0  # 50/30s vs 5/30s
    elapsed = time.time() - _last_request_time
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed)
    _last_request_time = time.time()


def _nvd_request(params: dict) -> dict:
    api_key = os.environ.get("NVD_API_KEY")
    headers = {"apiKey": api_key} if api_key else {}
    url = f"{NVD_API_BASE}?{urllib.parse.urlencode(params)}"
    _rate_limit()

    req = urllib.request.Request(url, headers={**headers, "User-Agent": "code-review-agent/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def _parse_cvss(vuln: dict) -> tuple[float | None, str]:
    metrics = vuln.get("metrics", {})
    for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        entries = metrics.get(key, [])
        if entries:
            data = entries[0].get("cvssData", {})
            score = data.get("baseScore")
            severity = data.get("baseSeverity", "")
            if not severity and score is not None:
                severity = _score_to_severity(score)
            return score, severity.upper()
    return None, ""


def _score_to_severity(score: float) -> str:
    if score >= 9.0: return "CRITICAL"
    if score >= 7.0: return "HIGH"
    if score >= 4.0: return "MEDIUM"
    return "LOW"


def lookup_by_cwe(cwe_id: str, keyword: str = "") -> CVEResult | None:
    """
    Find the most severe recent CVE matching a CWE ID.
    Optionally narrows results with a keyword (e.g. 'python', 'injection').
    """
    cwe_num = re.sub(r"[^0-9]", "", cwe_id)
    if not cwe_num:
        return None

    params = {
        "cweId": f"CWE-{cwe_num}",
        "resultsPerPage": 5,
        "startIndex": 0,
    }
    if keyword:
        params["keywordSearch"] = keyword
        params["keywordExactMatch"] = ""

    try:
        data = _nvd_request(params)
    except Exception:
        return None

    vulns = data.get("vulnerabilities", [])
    if not vulns:
        return None

    # Pick the highest CVSS score from results
    best = None
    best_score = -1.0
    for item in vulns:
        cve = item.get("cve", {})
        score, severity = _parse_cvss(cve)
        if score and score > best_score:
            best_score = score
            desc_list = cve.get("descriptions", [])
            desc = next((d["value"] for d in desc_list if d["lang"] == "en"), "")
            best = CVEResult(
                cve_id=cve.get("id", ""),
                description=desc[:300],
                cvss_score=score,
                cvss_severity=severity,
                url=f"https://nvd.nist.gov/vuln/detail/{cve.get('id', '')}",
            )
    return best


def lookup_by_cve_id(cve_id: str) -> CVEResult | None:
    """Direct lookup by CVE ID e.g. 'CVE-2024-1234'."""
    try:
        data = _nvd_request({"cveId": cve_id})
    except Exception:
        return None

    vulns = data.get("vulnerabilities", [])
    if not vulns:
        return None

    cve = vulns[0].get("cve", {})
    score, severity = _parse_cvss(cve)
    desc_list = cve.get("descriptions", [])
    desc = next((d["value"] for d in desc_list if d["lang"] == "en"), "")
    return CVEResult(
        cve_id=cve.get("id", ""),
        description=desc[:300],
        cvss_score=score,
        cvss_severity=severity,
        url=f"https://nvd.nist.gov/vuln/detail/{cve.get('id', '')}",
    )


def enrich_findings(findings) -> None:
    """
    In-place enrichment — adds CVE data to security findings that have a CWE.
    Only queries NVD for SECURITY category findings to conserve rate limit.
    """
    for f in findings:
        if f.category != "SECURITY" or not f.cwe:
            continue
        try:
            # Extract keyword from problem text for better NVD match
            keyword = _extract_keyword(f.problem)
            result = lookup_by_cwe(f.cwe, keyword=keyword)
            if result:
                f.cve_id = result.cve_id
                f.cvss_score = result.cvss_score
                f.cvss_severity = result.cvss_severity
                f.cve_description = result.description
        except Exception:
            continue


def _extract_keyword(problem: str) -> str:
    """Pull a useful search keyword from the problem description."""
    keywords = ["injection", "sql", "command", "pickle", "deserializ",
                "credential", "token", "password", "tls", "ssl", "crypto",
                "xss", "path traversal", "ssrf"]
    lower = problem.lower()
    for kw in keywords:
        if kw in lower:
            return kw
    return ""
