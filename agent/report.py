"""
Generates a self-contained HTML audit report from a stored review.
Suitable for attaching to a PR, emailing, or storing as a compliance artefact.
"""

from datetime import datetime
from pathlib import Path


SEVERITY_COLORS = {
    "BLOCKER": "#FF4B4B",
    "HIGH": "#FF8C00",
    "MEDIUM": "#FFC107",
    "LOW": "#4CAF50",
    "INFO": "#2196F3",
}

VERDICT_COLORS = {
    "APPROVE": "#4CAF50",
    "APPROVE WITH MINOR NOTES": "#8BC34A",
    "REQUEST CHANGES": "#FF8C00",
    "BLOCK": "#FF4B4B",
}

STATUS_LABELS = {
    "open": ("🔴", "Open"),
    "fixed": ("✅", "Fixed"),
    "accepted_risk": ("⚠️", "Accepted Risk"),
    "false_positive": ("🔕", "False Positive"),
}


def _finding_row(f) -> str:
    color = SEVERITY_COLORS.get(f["severity"], "#888")
    icon, status_label = STATUS_LABELS.get(f["status"], ("🔴", f["status"]))
    location = f["file"] or ""
    if f["line"]:
        location += f"  line {f['line']}"

    current_block = ""
    if f["current_code"]:
        current_block = f"""
        <div class="code-label">❌ Current code</div>
        <pre><code>{_esc(f["current_code"])}</code></pre>"""

    fix_block = ""
    if f["fix"]:
        fix_block = f"""
        <div class="code-label">✅ Change to</div>
        <pre class="fix"><code>{_esc(f["fix"])}</code></pre>"""

    # OWASP / CWE / CVE tags
    framework_tags = ""
    if f.get("owasp"):
        framework_tags += f'<span class="fw-tag owasp">OWASP {_esc(f["owasp"])}</span>'
    if f.get("cwe"):
        framework_tags += f'<span class="fw-tag cwe">{_esc(f["cwe"])}</span>'
    if f.get("cve_id"):
        cvss = f.get("cvss_score", "")
        sev = f.get("cvss_severity", "")
        cvss_color = {"CRITICAL": "#FF4B4B", "HIGH": "#FF8C00", "MEDIUM": "#FFC107", "LOW": "#4CAF50"}.get(sev, "#888")
        framework_tags += (
            f'<span class="fw-tag" style="color:{cvss_color}">'
            f'🔗 {_esc(f["cve_id"])}'
            f'{f" · CVSS {cvss}" if cvss else ""}'
            f'{f" {sev}" if sev else ""}'
            f'</span>'
        )

    cve_desc = ""
    if f.get("cve_description"):
        cve_desc = f'<div class="cve-desc">NVD: {_esc(f["cve_description"])}</div>'

    return f"""
    <div class="finding" style="border-left-color:{color}">
      <div class="finding-header">
        <span class="badge" style="background:{color}">{f["severity"]}</span>
        <span class="cat-tag">{f["category"]}</span>
        {f'<span class="location">📄 {_esc(location)}</span>' if location else ""}
        <span class="status-tag">{icon} {status_label}</span>
      </div>
      {f'<div class="framework-tags">{framework_tags}</div>' if framework_tags else ""}
      {cve_desc}
      {f'<div class="field-label">What is wrong</div><p>{_esc(f["problem"])}</p>' if f["problem"] else ""}
      {f'<div class="field-label">Why it matters</div><p>{_esc(f["impact"])}</p>' if f["impact"] else ""}
      {current_block}
      {fix_block}
      {f'<div class="status-note"><em>Note: {_esc(f["status_note"])}</em></div>' if f.get("status_note") else ""}
    </div>"""


def _esc(s: str) -> str:
    if not s:
        return ""
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;"))


def generate_html_report(review: dict, findings: list) -> str:
    verdict = review.get("verdict") or "N/A"
    verdict_color = VERDICT_COLORS.get(verdict, "#888")
    created = review.get("created_at", "")[:19].replace("T", " ")
    blocker_count = sum(1 for f in findings if f["severity"] == "BLOCKER")
    open_count = sum(1 for f in findings if f["status"] == "open")
    fixed_count = sum(1 for f in findings if f["status"] == "fixed")
    accepted_count = sum(1 for f in findings if f["status"] == "accepted_risk")
    fp_count = sum(1 for f in findings if f["status"] == "false_positive")

    findings_html = "".join(_finding_row(f) for f in findings) if findings else "<p>No findings.</p>"

    git_section = ""
    if review.get("git_commit"):
        git_section = f"""
        <tr><td>Branch</td><td>{_esc(review.get("git_branch") or "—")}</td></tr>
        <tr><td>Commit</td><td><code>{_esc(review.get("git_commit") or "—")}</code></td></tr>
        <tr><td>Author</td><td>{_esc(review.get("git_author") or "—")}</td></tr>"""

    signed_off_at = (review.get("signed_off_at") or "")[:19].replace("T", " ")
    if review.get("reviewer_name"):
        signoff_section = f"""
        <tr><td>Signed off by</td>
            <td><strong style="color:#4CAF50">✅ {_esc(review["reviewer_name"])}</strong>
            &nbsp; at {signed_off_at} UTC</td></tr>"""
    else:
        signoff_section = """
        <tr><td>Signed off by</td>
            <td><span style="color:#FF8C00">⏳ Not signed off</span></td></tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Code Review Audit Report</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         background:#0f0f1a; color:#e0e0e0; margin:0; padding:32px; }}
  .container {{ max-width:960px; margin:0 auto; }}
  h1 {{ color:#fff; border-bottom:2px solid #333; padding-bottom:12px; }}
  h2 {{ color:#aaa; font-size:1em; text-transform:uppercase; letter-spacing:.1em; margin-top:32px; }}
  .verdict {{ display:inline-block; padding:10px 24px; border-radius:6px;
              font-size:1.3em; font-weight:800; color:#fff;
              background:{verdict_color}; margin:16px 0; }}
  .meta-table {{ border-collapse:collapse; width:100%; margin:12px 0; }}
  .meta-table td {{ padding:6px 12px; border:1px solid #2a2a3e; }}
  .meta-table td:first-child {{ color:#888; width:160px; }}
  .stats {{ display:flex; gap:16px; margin:16px 0; flex-wrap:wrap; }}
  .stat {{ background:#1a1a2e; border-radius:8px; padding:12px 20px; text-align:center; min-width:90px; }}
  .stat .n {{ font-size:2em; font-weight:700; }}
  .stat .label {{ font-size:.72em; color:#888; margin-top:4px; }}
  .finding {{ border-left:4px solid #555; background:#1a1a2e;
              border-radius:6px; padding:16px 20px; margin:12px 0; }}
  .finding-header {{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-bottom:12px; }}
  .badge {{ padding:3px 10px; border-radius:4px; font-size:.8em; font-weight:700; color:#fff; }}
  .cat-tag {{ background:#2a2a3e; padding:2px 8px; border-radius:4px;
              font-size:.75em; color:#aaa; font-weight:600; }}
  .location {{ font-size:.8em; color:#7ec8e3; font-family:monospace; }}
  .status-tag {{ margin-left:auto; font-size:.8em; color:#aaa; }}
  .field-label {{ font-size:.7em; text-transform:uppercase; letter-spacing:.1em;
                  color:#666; margin:10px 0 4px; }}
  pre {{ background:#111; border-radius:4px; padding:12px; overflow-x:auto;
         font-size:.85em; margin:6px 0; }}
  pre.fix {{ border-left:3px solid #4CAF50; }}
  .code-label {{ font-size:.72em; color:#888; margin-top:10px; }}
  .status-note {{ font-size:.85em; color:#aaa; margin-top:8px; }}
  .framework-tags {{ display:flex; gap:6px; flex-wrap:wrap; margin-bottom:10px; }}
  .fw-tag {{ font-size:.72em; font-weight:700; padding:2px 8px; border-radius:4px;
             background:#2a2a3e; color:#ccc; font-family:monospace; }}
  .fw-tag.owasp {{ background:#1a2a3e; color:#7ec8e3; }}
  .fw-tag.cwe  {{ background:#2a1a3e; color:#b39ddb; }}
  .cve-desc {{ font-size:.8em; color:#aaa; margin:4px 0 8px; font-style:italic; }}
  .summary-box {{ background:#1a1a2e; border-radius:6px; padding:16px 20px;
                  border-left:4px solid #555; margin:12px 0; line-height:1.6; }}
  .positive-box {{ background:#1a2e1a; border-radius:6px; padding:16px 20px;
                   border-left:4px solid #4CAF50; margin:12px 0; line-height:1.6; }}
  .footer {{ margin-top:48px; padding-top:16px; border-top:1px solid #2a2a3e;
             font-size:.8em; color:#555; }}
</style>
</head>
<body>
<div class="container">
  <h1>Code Review Audit Report</h1>

  <div class="verdict">{_esc(verdict)}</div>

  <h2>Review Metadata</h2>
  <table class="meta-table">
    <tr><td>Target</td><td><code>{_esc(review.get("target",""))}</code></td></tr>
    <tr><td>Reviewed at</td><td>{created} UTC</td></tr>
    <tr><td>Provider</td><td>{_esc(review.get("provider",""))}</td></tr>
    <tr><td>Smart mode</td><td>{"Yes" if review.get("smart_mode") else "No"}</td></tr>
    {git_section}
    {signoff_section}
  </table>

  <h2>Finding Summary</h2>
  <div class="stats">
    <div class="stat">
      <div class="n" style="color:#FF4B4B">{blocker_count}</div>
      <div class="label">🚨 Blockers</div>
    </div>
    <div class="stat">
      <div class="n" style="color:#eee">{len(findings)}</div>
      <div class="label">Total findings</div>
    </div>
    <div class="stat">
      <div class="n" style="color:#FF4B4B">{open_count}</div>
      <div class="label">🔴 Open</div>
    </div>
    <div class="stat">
      <div class="n" style="color:#4CAF50">{fixed_count}</div>
      <div class="label">✅ Fixed</div>
    </div>
    <div class="stat">
      <div class="n" style="color:#FFC107">{accepted_count}</div>
      <div class="label">⚠️ Accepted</div>
    </div>
    <div class="stat">
      <div class="n" style="color:#888">{fp_count}</div>
      <div class="label">🔕 False +ve</div>
    </div>
  </div>

  {f'<h2>Summary</h2><div class="summary-box">{_esc(review.get("summary",""))}</div>' if review.get("summary") else ""}

  <h2>Findings ({len(findings)})</h2>
  {findings_html}

  {f'<h2>Positive Notes</h2><div class="positive-box">{_esc(review.get("positive_notes",""))}</div>' if review.get("positive_notes") else ""}

  <div class="footer">
    Generated by Code Review Agent &nbsp;·&nbsp; Review ID #{review.get("id")} &nbsp;·&nbsp; {created} UTC
  </div>
</div>
</body>
</html>"""
