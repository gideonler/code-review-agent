"""
Streamlit UI for the code review agent.
Run with: streamlit run ui/app.py
"""

import sys
import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

from agent.reviewer import review_target
from agent.parser import (
    parse_review,
    ReviewResult,
    Finding,
    Severity,
    Verdict,
    SEVERITY_COLORS,
    VERDICT_COLORS,
    SEVERITY_ORDER,
)
from agent.store import list_reviews, get_review, update_finding_status, review_stats, init_db
from agent.report import generate_html_report

init_db()

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Sentinel — Code Review",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Design system ─────────────────────────────────────────────────────────────

st.markdown("""
<style>
/* ── Base ── */
[data-testid="stAppViewContainer"] {
    background: #080810;
}
[data-testid="stSidebar"] {
    background: #0d0d1a !important;
    border-right: 1px solid #1a1a2e;
}
[data-testid="stSidebar"] > div:first-child {
    padding-top: 1.5rem;
}
.block-container {
    padding: 2rem 2.5rem 4rem;
    max-width: 1280px;
}

/* ── Typography ── */
h1, h2, h3 {
    color: #f0f0ff !important;
    letter-spacing: -0.02em;
}
p, li, label, .stMarkdown {
    color: #b0b0cc;
}

/* ── Sidebar labels ── */
[data-testid="stSidebar"] label {
    font-size: 0.78em !important;
    font-weight: 600 !important;
    letter-spacing: 0.06em !important;
    text-transform: uppercase !important;
    color: #5a5a7a !important;
}
[data-testid="stSidebar"] .stSelectbox > div > div,
[data-testid="stSidebar"] .stTextInput > div > div > input,
[data-testid="stSidebar"] .stTextArea > div > div > textarea {
    background: #13131f !important;
    border: 1px solid #1e1e35 !important;
    color: #d0d0ee !important;
    border-radius: 8px !important;
}
[data-testid="stSidebar"] .stTextInput > div > div > input:focus,
[data-testid="stSidebar"] .stTextArea > div > div > textarea:focus {
    border-color: #4f46e5 !important;
    box-shadow: 0 0 0 2px rgba(79,70,229,0.2) !important;
}

/* ── Primary button ── */
.stButton > button[kind="primary"] {
    background: #4f46e5 !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 700 !important;
    letter-spacing: 0.03em !important;
    padding: 0.6rem 1rem !important;
    color: white !important;
    transition: all 0.15s ease !important;
    box-shadow: 0 2px 8px rgba(79,70,229,0.35) !important;
}
.stButton > button[kind="primary"]:hover {
    background: #4338ca !important;
    box-shadow: 0 4px 16px rgba(79,70,229,0.5) !important;
    transform: translateY(-1px) !important;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    background: transparent !important;
    border-bottom: 1px solid #1a1a2e !important;
    gap: 0 !important;
}
.stTabs [data-baseweb="tab"] {
    color: #6060a0 !important;
    font-weight: 600 !important;
    font-size: 0.85em !important;
    letter-spacing: 0.04em !important;
    padding: 0.6rem 1.2rem !important;
    border-radius: 0 !important;
    border-bottom: 2px solid transparent !important;
}
.stTabs [aria-selected="true"] {
    color: #a0a0f0 !important;
    border-bottom: 2px solid #4f46e5 !important;
    background: transparent !important;
}

/* ── Cards ── */
[data-testid="stVerticalBlock"] > [data-testid="stVerticalBlock"] > div > [data-testid="element-container"] > div[style*="border"] {
    background: #0f0f1e !important;
    border-color: #1e1e35 !important;
    border-radius: 12px !important;
}

/* ── Metrics ── */
[data-testid="stMetric"] {
    background: #0f0f1e;
    border: 1px solid #1a1a30;
    border-radius: 12px;
    padding: 16px 20px;
}
[data-testid="stMetricLabel"] { color: #6060a0 !important; font-size: 0.78em !important; font-weight: 600 !important; text-transform: uppercase !important; letter-spacing: 0.06em !important; }
[data-testid="stMetricValue"] { color: #e0e0ff !important; }

/* ── Code blocks ── */
.stCodeBlock { border-radius: 8px !important; }
pre {
    background: #0a0a14 !important;
    border: 1px solid #1a1a2e !important;
    border-radius: 8px !important;
}

/* ── Expander ── */
[data-testid="stExpander"] {
    background: #0f0f1e !important;
    border: 1px solid #1a1a30 !important;
    border-radius: 10px !important;
}
[data-testid="stExpander"] summary {
    color: #9090c0 !important;
    font-weight: 600 !important;
}

/* ── Finding card ── */
.finding-card {
    background: #0f0f1e;
    border: 1px solid #1e1e35;
    border-radius: 12px;
    padding: 20px 24px;
    margin: 10px 0;
    transition: border-color 0.15s ease;
}
.finding-card:hover {
    border-color: #2e2e55;
}
.finding-header {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 14px;
}
.sev-badge {
    display: inline-block;
    padding: 3px 12px;
    border-radius: 6px;
    font-size: 0.75em;
    font-weight: 800;
    color: white;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}
.cat-pill {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 0.72em;
    font-weight: 700;
    background: #1a1a30;
    color: #8080b0;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}
.file-loc {
    font-size: 0.78em;
    color: #64b5f6;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    background: #0d1a2a;
    padding: 2px 8px;
    border-radius: 4px;
}
.fw-row {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    margin: 8px 0 12px;
}
.fw-chip {
    font-size: 0.72em;
    font-weight: 700;
    padding: 3px 10px;
    border-radius: 6px;
    font-family: monospace;
    letter-spacing: 0.03em;
}
.fw-owasp { background: #0d1535; color: #7eb3f7; border: 1px solid #1a2e5a; }
.fw-cwe   { background: #160d35; color: #b39ddb; border: 1px solid #2a1a5a; }
.fw-cve   { border: 1px solid; }
.field-lbl {
    font-size: 0.68em;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #4a4a70;
    margin: 14px 0 4px;
}
.cve-desc-box {
    font-size: 0.8em;
    color: #7070a0;
    font-style: italic;
    padding: 8px 12px;
    background: #0d0d18;
    border-left: 3px solid #2a2a50;
    border-radius: 0 6px 6px 0;
    margin: 8px 0;
}

/* ── Verdict banner ── */
.verdict-banner {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 16px 24px;
    border-radius: 12px;
    margin-bottom: 24px;
}
.verdict-banner .v-label {
    font-size: 0.7em;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    opacity: 0.7;
}
.verdict-banner .v-text {
    font-size: 1.35em;
    font-weight: 800;
    color: white;
    letter-spacing: -0.01em;
}

/* ── Stats strip ── */
.stat-card {
    background: #0f0f1e;
    border: 1px solid #1a1a30;
    border-radius: 10px;
    padding: 14px 18px;
    text-align: center;
}
.stat-n {
    font-size: 2em;
    font-weight: 800;
    line-height: 1;
}
.stat-lbl {
    font-size: 0.68em;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #4a4a70;
    margin-top: 6px;
}

/* ── Section heading ── */
.sec-heading {
    font-size: 0.72em;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #4a4a70;
    margin: 28px 0 12px;
    border-bottom: 1px solid #1a1a2e;
    padding-bottom: 8px;
}

/* ── Page title ── */
.page-title {
    font-size: 1.6em;
    font-weight: 800;
    color: #f0f0ff;
    letter-spacing: -0.03em;
    margin-bottom: 2px;
}
.page-sub {
    font-size: 0.85em;
    color: #4a4a70;
    margin-bottom: 28px;
}

/* ── Audit row ── */
.audit-row {
    background: #0f0f1e;
    border: 1px solid #1a1a30;
    border-radius: 10px;
    padding: 14px 18px;
    margin: 6px 0;
}
.audit-row:hover {
    border-color: #2a2a45;
}

/* ── Triage tag ── */
.triage-open   { color: #ef5350; }
.triage-fixed  { color: #66bb6a; }
.triage-accept { color: #ffa726; }
.triage-fp     { color: #78909c; }

/* ── Sidebar branding ── */
.sidebar-brand {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 6px;
}
.sidebar-brand-name {
    font-size: 1.1em;
    font-weight: 800;
    color: #e0e0ff;
    letter-spacing: -0.02em;
}
.sidebar-brand-sub {
    font-size: 0.72em;
    color: #4a4a70;
    letter-spacing: 0.04em;
    margin-bottom: 20px;
}

/* ── Divider ── */
hr {
    border-color: #1a1a2e !important;
    margin: 16px 0 !important;
}

/* ── Info/warning/error boxes ── */
[data-testid="stAlert"] {
    border-radius: 8px !important;
    border: 1px solid !important;
}
</style>
""", unsafe_allow_html=True)


# ── Sidebar ───────────────────────────────────────────────────────────────────

_PROVIDER_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini":    "GEMINI_API_KEY",
    "groq":      "GROQ_API_KEY",
}

with st.sidebar:
    st.markdown("""
    <div class="sidebar-brand">
        <span style="font-size:1.4em">🛡️</span>
        <span class="sidebar-brand-name">Sentinel</span>
    </div>
    <div class="sidebar-brand-sub">AI Code Review &amp; Audit</div>
    """, unsafe_allow_html=True)

    st.divider()

    input_mode = st.radio("Input mode", ["File path", "Paste code"], index=0)

    if input_mode == "File path":
        target_input = st.text_input("File or directory path", placeholder="/path/to/project")
    else:
        pasted_code = st.text_area("Paste code", height=260)
        lang_hint = st.selectbox("Language", ["python", "golang", "sql", "bash", "typescript", "other"])

    st.divider()

    selected_provider = st.selectbox(
        "AI provider",
        options=["anthropic", "gemini", "groq"],
        format_func=lambda x: {"anthropic": "Anthropic — Claude", "gemini": "Google — Gemini", "groq": "Groq — LLaMA"}[x],
    )
    env_var = _PROVIDER_KEY_ENV.get(selected_provider, "API_KEY")
    api_key_input = st.text_input(
        f"API key ({env_var})",
        type="password",
        placeholder="Leave blank to use .env",
    )
    if api_key_input:
        os.environ[env_var] = api_key_input

    st.divider()

    c1, c2 = st.columns(2)
    with c1:
        diff_mode = st.toggle("Diff mode", value=False, help="Review only git-changed lines — ideal for PRs.")
    with c2:
        smart_mode = st.toggle("Smart mode", value=False, help="Strips comments, skips tests, ~40% fewer tokens.")

    if diff_mode:
        diff_ref = st.text_input("Compare against", value="HEAD~1", help="e.g. HEAD~1, main, a3b4c5d")
    else:
        diff_ref = None

    st.divider()

    reviewer_name = st.text_input(
        "Sign-off name",
        placeholder="e.g. Gideon Ler",
        help="Stamped on the audit record as the approving engineer.",
    )

    run_btn = st.button("Run Review", type="primary", use_container_width=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

_SEV_ICONS = {
    Severity.BLOCKER: "🚨",
    Severity.HIGH:    "⚠️",
    Severity.MEDIUM:  "🔶",
    Severity.LOW:     "💡",
    Severity.INFO:    "ℹ️",
}

_SEV_LABELS = {
    Severity.BLOCKER: "Must fix",
    Severity.HIGH:    "Should fix",
    Severity.MEDIUM:  "Fix soon",
    Severity.LOW:     "Suggestion",
    Severity.INFO:    "Info",
}

_VERDICT_ICONS = {
    "APPROVE":                "✅",
    "APPROVE WITH MINOR NOTES": "✅",
    "REQUEST CHANGES":        "⚠️",
    "BLOCK":                  "🚫",
}


def _cvss_color(sev: str) -> str:
    return {"CRITICAL": "#ef5350", "HIGH": "#ff7043", "MEDIUM": "#ffa726", "LOW": "#66bb6a"}.get(sev, "#888")


def render_finding(f: Finding):
    color = SEVERITY_COLORS.get(f.severity, "#555")
    location = f.file or ""
    if f.line:
        location += f" · line {f.line}"

    # Framework tags HTML
    fw_html = ""
    if getattr(f, "owasp", ""):
        fw_html += f'<span class="fw-chip fw-owasp">OWASP {f.owasp}</span>'
    if getattr(f, "cwe", ""):
        fw_html += f'<span class="fw-chip fw-cwe">{f.cwe}</span>'
    if getattr(f, "cve_id", ""):
        cc = _cvss_color(getattr(f, "cvss_severity", ""))
        cvss = f.cvss_score
        sev  = getattr(f, "cvss_severity", "")
        fw_html += (
            f'<span class="fw-chip fw-cve" style="color:{cc};border-color:{cc}22;background:{cc}11">'
            f'🔗 {f.cve_id}'
            f'{f" · CVSS {cvss}" if cvss else ""}'
            f'{f" · {sev}" if sev else ""}'
            f'</span>'
        )

    header_html = f"""
    <div class="finding-card">
      <div class="finding-header">
        <span class="sev-badge" style="background:{color}">{f.severity.value}</span>
        <span class="cat-pill">{f.category}</span>
        {f'<span class="file-loc">📄 {location}</span>' if location else ''}
      </div>
      {f'<div class="fw-row">{fw_html}</div>' if fw_html else ''}
      {f'<div class="cve-desc-box">NVD: {f.cve_description}</div>' if getattr(f, "cve_description", "") else ''}
    """

    if f.problem:
        header_html += f'<div class="field-lbl">What is wrong</div><p style="color:#c0c0e0;margin:4px 0 12px;line-height:1.6">{f.problem}</p>'
    if f.impact:
        header_html += f'<div class="field-lbl">Why it matters</div><p style="color:#c0c0e0;margin:4px 0 12px;line-height:1.6">{f.impact}</p>'

    header_html += "</div>"
    st.markdown(header_html, unsafe_allow_html=True)

    # Code blocks rendered via st.code for proper syntax highlighting
    if f.current_code or f.fix:
        if f.current_code and f.fix:
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown('<div class="field-lbl">❌ Current code</div>', unsafe_allow_html=True)
                st.code(f.current_code, language="python")
            with col_b:
                st.markdown('<div class="field-lbl">✅ Change to</div>', unsafe_allow_html=True)
                st.code(f.fix, language="python")
        elif f.fix:
            st.markdown('<div class="field-lbl">✅ Recommended fix</div>', unsafe_allow_html=True)
            st.code(f.fix, language="python")


def render_result(result: ReviewResult):
    # Verdict banner
    if result.verdict:
        vc = VERDICT_COLORS.get(result.verdict, "#888")
        vi = _VERDICT_ICONS.get(result.verdict.value if hasattr(result.verdict, "value") else result.verdict, "")
        vt = result.verdict.value if hasattr(result.verdict, "value") else result.verdict
        st.markdown(f"""
        <div class="verdict-banner" style="background:{vc}18;border:1px solid {vc}44">
            <span style="font-size:1.8em">{vi}</span>
            <div>
                <div class="v-label">Verdict</div>
                <div class="v-text" style="color:{vc}">{vt}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # Summary
    if result.summary:
        with st.expander("Summary", expanded=True):
            st.write(result.summary)

    # Stats strip
    if result.findings:
        st.markdown('<div class="sec-heading">Finding breakdown</div>', unsafe_allow_html=True)
        cols = st.columns(5)
        for col, sev in zip(cols, [Severity.BLOCKER, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO]):
            count = sum(1 for f in result.findings if f.severity == sev)
            color = SEVERITY_COLORS[sev]
            col.markdown(
                f'<div class="stat-card">'
                f'<div class="stat-n" style="color:{color}">{count}</div>'
                f'<div class="stat-lbl">{_SEV_ICONS[sev]} {_SEV_LABELS[sev]}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # Filters + findings
    if result.findings:
        st.markdown('<div class="sec-heading">All issues</div>', unsafe_allow_html=True)
        all_cats = sorted({f.category for f in result.findings})
        fc1, fc2 = st.columns([1, 2])
        with fc1:
            sev_filter = st.selectbox("Severity", ["All"] + [s.value for s in Severity], index=0, key="sev_filter")
        with fc2:
            cat_filter = st.selectbox("Category", ["All"] + all_cats, index=0, key="cat_filter")

        filtered = [
            f for f in result.findings_by_severity
            if (sev_filter == "All" or f.severity.value == sev_filter)
            and (cat_filter == "All" or f.category == cat_filter)
        ]
        st.caption(f"{len(filtered)} of {len(result.findings)} findings shown")

        for f in filtered:
            render_finding(f)

    # Positive notes
    if result.positive_notes:
        st.markdown('<div class="sec-heading">Positive notes</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div style="background:#0d1a0d;border:1px solid #1a3a1a;border-radius:10px;padding:16px 20px;color:#a5d6a7;line-height:1.7">{result.positive_notes}</div>',
            unsafe_allow_html=True,
        )

    # Raw output
    with st.expander("Raw output", expanded=False):
        st.text(result.raw)
        st.download_button("Download as Markdown", data=result.raw, file_name="code_review.md", mime="text/markdown")


# ── Main ──────────────────────────────────────────────────────────────────────

st.markdown('<div class="page-title">🛡️ Sentinel</div>', unsafe_allow_html=True)
st.markdown('<div class="page-sub">AI-powered code review · Senior DE + AppSec perspective</div>', unsafe_allow_html=True)

if "result" not in st.session_state:
    st.session_state.result = None
if "raw_review" not in st.session_state:
    st.session_state.raw_review = ""

if st.session_state.result:
    findings = st.session_state.result.findings
    if findings and not hasattr(findings[0], "current_code"):
        st.session_state.result = None
        st.session_state.raw_review = ""

tab_review, tab_history = st.tabs(["🔍  Review", "📋  Audit History"])

# ── Review tab ────────────────────────────────────────────────────────────────

with tab_review:
    if run_btn:
        required_env = _PROVIDER_KEY_ENV.get(selected_provider, "API_KEY")
        if not os.environ.get(required_env):
            st.error(f"**{required_env}** is not set — add it to `.env` or enter it in the sidebar.")
            st.stop()

        if input_mode == "Paste code":
            if not pasted_code.strip():
                st.error("Paste some code first.")
                st.stop()
            import tempfile
            ext_map = {"python": ".py", "golang": ".go", "sql": ".sql", "bash": ".sh", "typescript": ".ts", "other": ".txt"}
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=ext_map.get(lang_hint, ".txt"), delete=False, encoding="utf-8")
            tmp.write(pasted_code)
            tmp.flush()
            target = tmp.name
        else:
            target = target_input.strip()
            if not target or not Path(target).exists():
                st.error(f"Path not found: `{target}`")
                st.stop()

        st.session_state.result = None
        st.session_state.raw_review = ""
        st.session_state.review_id = None

        stream_placeholder = st.empty()
        raw_text = ""

        mode_tags = []
        if smart_mode: mode_tags.append("smart mode")
        if diff_mode:  mode_tags.append("diff mode")
        mode_str = "  ·  " + "  ·  ".join(mode_tags) if mode_tags else ""

        with st.spinner(f"Reviewing with {selected_provider}{mode_str} …"):
            try:
                for _, _, delta in review_target(target, stream=True, provider_name=selected_provider, smart=smart_mode, diff_ref=diff_ref):
                    raw_text += delta
                    stream_placeholder.markdown(
                        f'<div style="background:#0a0a14;border:1px solid #1a1a2e;border-radius:8px;padding:14px 18px;font-family:monospace;font-size:0.8em;color:#7070a0;max-height:320px;overflow:hidden">{raw_text[-2000:]}</div>',
                        unsafe_allow_html=True,
                    )
            except Exception as e:
                st.error(f"Review failed: {e}")
                st.stop()

        stream_placeholder.empty()
        st.session_state.raw_review = raw_text
        parsed = parse_review(raw_text)
        st.session_state.result = parsed

        try:
            from agent.store import save_review
            from agent.git_meta import get_git_meta
            meta = get_git_meta(target)
            review_id = save_review(
                result=parsed, target=target, provider=selected_provider,
                smart_mode=smart_mode, git_branch=meta.branch,
                git_commit=meta.commit, git_author=meta.author,
                reviewer_name=reviewer_name.strip() or None,
            )
            st.session_state.review_id = review_id
            if reviewer_name.strip():
                st.success(f"Saved & signed off by **{reviewer_name.strip()}** — Review #{review_id}")
            else:
                st.info(f"Saved to audit log — Review #{review_id} · No sign-off")
        except Exception:
            pass

    if st.session_state.result:
        render_result(st.session_state.result)
    elif not run_btn:
        st.markdown("""
        <div style="text-align:center;padding:80px 20px;color:#3a3a5a">
            <div style="font-size:3em;margin-bottom:16px">🛡️</div>
            <div style="font-size:1.1em;font-weight:600;color:#5a5a8a;margin-bottom:8px">Ready to review</div>
            <div style="font-size:0.85em">Enter a file path or paste code in the sidebar, then click <strong style="color:#6060a0">Run Review</strong>.</div>
        </div>
        """, unsafe_allow_html=True)

# ── Audit History tab ─────────────────────────────────────────────────────────

with tab_history:
    st.markdown('<div class="sec-heading">Compliance dashboard</div>', unsafe_allow_html=True)

    try:
        stats = review_stats()
        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("Total Reviews",  stats["total_reviews"])
        mc2.metric("Open Blockers",  stats["open_blockers"])
        mc3.metric("Approved",       stats["verdicts"].get("APPROVE", 0) + stats["verdicts"].get("APPROVE WITH MINOR NOTES", 0))
        mc4.metric("Blocked",        stats["verdicts"].get("BLOCK", 0))
    except Exception:
        pass

    st.markdown('<div class="sec-heading">Review history</div>', unsafe_allow_html=True)

    reviews = list_reviews(limit=100)
    if not reviews:
        st.markdown("""
        <div style="text-align:center;padding:60px 20px;color:#3a3a5a">
            <div style="font-size:2em;margin-bottom:12px">📋</div>
            <div style="font-size:0.9em">No reviews yet — run your first review to start the audit trail.</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        _STATUS_DOT = {"open": "🔴", "fixed": "🟢", "accepted_risk": "🟡", "false_positive": "⚫"}
        _VERDICT_DOT = {"APPROVE": "🟢", "APPROVE WITH MINOR NOTES": "🟡", "REQUEST CHANGES": "🟠", "BLOCK": "🔴"}

        for r in reviews:
            verdict     = r["verdict"] or "N/A"
            vdot        = _VERDICT_DOT.get(verdict, "⚪")
            created     = r["created_at"][:19].replace("T", " ")
            signoff_txt = f"✅ {r['reviewer_name']}" if r["reviewer_name"] else "⏳ Unsigned"
            fname       = Path(r["target"]).name
            label       = f"{vdot} **{verdict}** &nbsp;·&nbsp; `{fname}` &nbsp;·&nbsp; {created} &nbsp;·&nbsp; {signoff_txt}"
            if r["git_commit"]:
                label += f" &nbsp;·&nbsp; `{r['git_branch']}@{r['git_commit']}`"

            with st.expander(label):
                mc, ac = st.columns([2, 1])

                with mc:
                    st.markdown(f"**Target:** `{r['target']}`")
                    st.markdown(f"**Provider:** {r['provider']}  ·  **Smart mode:** {'Yes' if r['smart_mode'] else 'No'}")
                    if r["git_commit"]:
                        st.markdown(f"**Branch:** `{r['git_branch']}`  ·  **Commit:** `{r['git_commit']}`  ·  **Author:** {r['git_author']}")
                    st.markdown(f"**Findings:** {r['finding_count']} total  ·  {r['blocker_count']} blockers")
                    if r["reviewer_name"]:
                        signed_at = (r["signed_off_at"] or "")[:19].replace("T", " ")
                        st.success(f"Signed off by **{r['reviewer_name']}** at {signed_at} UTC")
                    else:
                        st.warning("No sign-off — enter your name in the sidebar before running a review.")

                with ac:
                    try:
                        review_row, findings_rows = get_review(r["id"])
                        findings_list = [dict(f) for f in findings_rows]
                        html = generate_html_report(dict(review_row), findings_list)
                        st.download_button(
                            "📄 Download audit report",
                            data=html,
                            file_name=f"audit_review_{r['id']}.html",
                            mime="text/html",
                            key=f"dl_{r['id']}",
                            use_container_width=True,
                        )
                    except Exception:
                        pass

                # Findings triage
                try:
                    _, findings_rows = get_review(r["id"])
                    if findings_rows:
                        st.markdown('<div class="sec-heading" style="margin-top:16px">Findings triage</div>', unsafe_allow_html=True)
                        for f in findings_rows:
                            color = SEVERITY_COLORS.get(f["severity"], "#888")
                            tc1, tc2, tc3 = st.columns([4, 1, 2])
                            with tc1:
                                st.markdown(
                                    f'<span class="sev-badge" style="background:{color}">{f["severity"]}</span> '
                                    f'<span class="cat-pill">{f["category"]}</span> '
                                    f'<span style="font-size:.82em;color:#8080aa">{(f["problem"] or "")[:90]}</span>',
                                    unsafe_allow_html=True,
                                )
                            with tc2:
                                dot = _STATUS_DOT.get(f["status"], "⚪")
                                st.markdown(f'<span style="font-size:.8em;color:#6060a0">{dot} {f["status"]}</span>', unsafe_allow_html=True)
                            with tc3:
                                new_status = st.selectbox(
                                    "Update status",
                                    options=["open", "fixed", "accepted_risk", "false_positive"],
                                    index=["open", "fixed", "accepted_risk", "false_positive"].index(f["status"]),
                                    key=f"status_{f['id']}",
                                    label_visibility="collapsed",
                                )
                                if new_status != f["status"]:
                                    update_finding_status(f["id"], new_status)
                                    st.rerun()
                except Exception:
                    pass
