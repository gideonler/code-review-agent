# Code Review Agent

An AI-powered code review tool that reviews your code from two perspectives simultaneously:
- **Senior Data Engineer** — pipeline reliability, PySpark, Golang, AWS, schema integrity
- **Application Security Developer** — OWASP Top 10, secrets, injection, CTI/telemetry-specific risks

Built for the Ensign InfoSecurity engineering context: Python, PySpark, Golang, AWS.

---

## Setup

### 1. Clone and enter the repo

```bash
git clone <your-repo-url>
cd code-review-agent
```

### 2. Install dependencies

> Make sure you're in the right Python environment (e.g. your conda base env)

```bash
pip install anthropic streamlit python-dotenv click rich gitpython
```

Or install all at once:

```bash
pip install -r requirements.txt
```

### 3. Set your Anthropic API key

```bash
cp .env.example .env
```

Edit `.env` and add your key:

```
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxx
```

Get a key at [console.anthropic.com](https://console.anthropic.com).

---

## Usage

### CLI

Review a single file:

```bash
python main.py review path/to/file.py
```

Review an entire directory:

```bash
python main.py review path/to/project/
```

Save the review to a markdown file:

```bash
python main.py review path/to/project/ --output report.md
```

Run without streaming (wait for full response):

```bash
python main.py review path/to/file.py --no-stream
```

### Streamlit UI

```bash
streamlit run ui/app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

**In the sidebar:**
1. Choose **File path** and enter a path, or **Paste code** directly
2. Optionally enter your API key (overrides `.env`)
3. Click **Run Review**

The UI shows:
- Verdict banner (APPROVE / REQUEST CHANGES / BLOCK)
- Severity breakdown (BLOCKER / HIGH / MEDIUM / LOW / INFO)
- Filterable findings cards with Problem, Impact, and Fix
- Download button to export the report as Markdown

---

## What gets reviewed

The agent flags issues across these categories:

| Category | Examples |
|---|---|
| `SECURITY` | Hardcoded secrets, SQL injection, missing TLS, unsafe deserialization |
| `DATA_INTEGRITY` | Missing schema validation, silent type coercion, null handling gaps |
| `RELIABILITY` | Missing retries, no DLQ, non-idempotent jobs |
| `PYSPARK` | `collect()` on large datasets, cartesian joins, missing partitioning |
| `GOLANG` | Goroutine leaks, unchecked errors, missing context propagation |
| `AWS` | Overly permissive IAM, missing DLQs, hardcoded regions |
| `PERFORMANCE` | UDFs where native Spark functions exist, missing cache/persist |

Findings are rated: **BLOCKER** → **HIGH** → **MEDIUM** → **LOW** → **INFO**

---

## Project structure

```
code-review-agent/
├── CLAUDE.md           # System prompt — defines the dual DE + appsec persona
├── main.py             # CLI entrypoint
├── requirements.txt
├── .env.example
├── agent/
│   ├── chunker.py      # Reads files, batches into context-window-sized chunks
│   ├── reviewer.py     # Calls Claude API with streaming + prompt caching
│   └── parser.py       # Parses structured findings into typed objects
└── ui/
    └── app.py          # Streamlit UI
```

---

## Supported languages and file types

`.py` `.go` `.ts` `.tsx` `.js` `.jsx` `.java` `.scala` `.sql` `.sh` `.yaml` `.yml` `.tf` `.json` `.toml`

Skips: `.git/`, `__pycache__/`, `node_modules/`, `.venv/`, `dist/`, `build/`

---

## Tips

- **Large repos**: Point at a subdirectory (e.g. `src/`) rather than the repo root to keep reviews focused
- **Paste mode**: Great for reviewing a single function or script without needing a file path
- **Reports**: Use `--output report.md` to save reviews and track findings over time
- **CLAUDE.md**: Edit this file to tune the review rules, add new categories, or adjust severity thresholds
# test
