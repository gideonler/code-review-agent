# Code Review Agent

An AI-powered code review tool that reviews your code from two perspectives simultaneously:
- **Senior Data Engineer** — pipeline reliability, PySpark, Golang, AWS, schema integrity
- **Application Security Developer** — OWASP Top 10, secrets, injection, CTI/telemetry-specific risks

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
├── .gitlab-ci.yml      # GitLab MR review (artifact + optional MR note)
├── requirements.txt
├── .env.example
├── scripts/
│   └── post_gitlab_mr_note.py  # Posts review.md to GitLab MR (GITLAB_TOKEN)
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

## GitLab merge request review (CI)

The repo includes **`.gitlab-ci.yml`**: on every **merge request** pipeline it reviews the **diff vs the target branch** and writes **`review.md`** as a job artifact. Pipelines run for **merge request events** only (opening or updating an MR), not for arbitrary branch pushes with no MR.

### Quick demo (step by step, no GitLab token)

You do **not** need **`GITLAB_TOKEN`**. Without it, the review appears only as the job artifact **`review.md`** (not as a discussion comment on the MR).

1. **Create a GitLab project** and push this repository so the project contains at least **`.gitlab-ci.yml`**, **`main.py`**, **`pyproject.toml`**, **`CLAUDE.md`**, **`agent/`**, and **`scripts/post_gitlab_mr_note.py`** (pushing the whole repo is simplest).
2. **Add your LLM key:** **Settings → CI/CD → Variables → Add variable**
   - **`ANTHROPIC_API_KEY`** — your key; enable **Mask variable**.
   - (Optional) To use Groq or Gemini instead, add **`SENTINEL_PROVIDER`** with value `groq` or `gemini`, and add **`GROQ_API_KEY`** or **`GEMINI_API_KEY`**.
   - (Optional) If runners need a corporate proxy to reach the API, add **`HTTPS_PROXY`** / **`HTTP_PROXY`** / **`NO_PROXY`**.
3. **Open a merge request:** create a branch from the default branch (e.g. `main`), change a file, push, then open an **MR** into that default branch. The pipeline starts when the MR exists (or when you push new commits to the MR branch).
4. **View the review:** on the MR go to **Pipelines** → open the latest pipeline → job **`sentinel_mr_review`** → **Job artifacts** → **Browse** (or download) → open **`review.md`**.

The job log may say that **`GITLAB_TOKEN`** is not set; that is expected and does not fail the job.

### Optional: post the review on the MR

If you want the markdown **posted as a discussion** on the merge request (and updated on each push), add a masked **`GITLAB_TOKEN`**: **Settings → Access tokens** (project access token) with **`api`** scope, then add it as a CI/CD variable named **`GITLAB_TOKEN`**.

### Separate “app repo” demo (recommended for showing it as a tool)

If you want a **separate repository** that contains only your application code (and not this agent), use the **app repo** CI to **clone this agent repo** at runtime and run it against the merge request diff.

1. **Create two GitLab projects**
   - **Agent repo**: `code-review-agent` (this repo). Make it **public** for the easiest demo, or keep it private and use a **read-only token** for cloning.
   - **App repo**: `my-app-demo` (any code you want to review).
2. In the **app repo**, add CI/CD variables (masked):
   - **`ANTHROPIC_API_KEY`** (or set `SENTINEL_PROVIDER=groq|gemini` and add the matching key).
   - If the agent repo is private: **`AGENT_CLONE_URL`** (a clone URL that already includes credentials; keep it masked).
   - (Optional) **`HTTPS_PROXY`** / `HTTP_PROXY` / `NO_PROXY` for corporate proxy.
3. In the **app repo**, create `.gitlab-ci.yml` by copying from:
   - **`examples/gitlab-app-repo/.gitlab-ci.yml`** in this repository.
4. Open a merge request in the **app repo**, then view the pipeline job artifact **`review.md`**.

### GitHub Actions

PR review via `gh` and `review.py` is documented in-repo under `.github/workflows/` (Sentinel-style). GitLab uses **`main.py review … --diff`** only; GitHub-specific comment code is not used.

---

## Tips

- **Large repos**: Point at a subdirectory (e.g. `src/`) rather than the repo root to keep reviews focused
- **Paste mode**: Great for reviewing a single function or script without needing a file path
- **Reports**: Use `--output report.md` to save reviews and track findings over time
- **CLAUDE.md**: Edit this file to tune the review rules, add new categories, or adjust severity thresholds
