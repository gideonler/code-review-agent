"""
Reads files from a path (single file or directory) and chunks them
into reviewable units that fit within the model's context window.
"""

import os
import re
import tokenize
import io
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_EXTENSIONS = {
    ".py", ".go", ".ts", ".tsx", ".js", ".jsx",
    ".java", ".scala", ".sql", ".sh", ".yaml", ".yml",
    ".tf", ".json", ".toml", ".env.example", ".dockerfile",
}

SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "dist", "build", ".idea", ".vscode",
}

# Files to skip entirely in smart mode — low signal, high tokens
SKIP_PATTERNS = {
    "*.lock", "poetry.lock", "package-lock.json", "yarn.lock",
    "*.min.js", "*.min.css", "*.pb.go", "*.pb.py",
}

# Higher score = reviewed first. Files not listed default to 50.
FILE_PRIORITY: dict[str, int] = {
    # Auth / secrets / credentials — highest risk
    "auth": 100, "credential": 100, "secret": 100, "token": 100,
    "password": 100, "api_key": 100, "apikey": 100,
    # Data pipeline entry points
    "pipeline": 90, "ingestion": 90, "ingest": 90, "etl": 90,
    "lambda": 85, "handler": 85, "glue": 85,
    # API surface
    "endpoint": 80, "route": 80, "api": 80, "view": 80, "controller": 80,
    # Config and infra
    "config": 70, "settings": 70, "terraform": 70,
    # General app code
    "main": 60, "app": 60, "server": 60,
    # Tests — low priority, skip in smart mode
    "test": 10, "spec": 10, "mock": 10, "fixture": 10,
}

# Default chunk limit for large-context providers (Anthropic, Gemini)
CHUNK_CHAR_LIMIT_DEFAULT = 240_000

# Groq free tier caps at ~12k TPM total per request.
# CLAUDE.md system prompt is ~4k tokens, leaving ~7k for content.
# 7k tokens * 4 chars/token = ~28k chars, but use 20k to stay safely under.
CHUNK_CHAR_LIMIT_GROQ = 20_000

PROVIDER_CHUNK_LIMITS: dict[str, int] = {
    "groq": CHUNK_CHAR_LIMIT_GROQ,
}


def get_chunk_limit(provider: str = "anthropic") -> int:
    return PROVIDER_CHUNK_LIMITS.get(provider, CHUNK_CHAR_LIMIT_DEFAULT)


@dataclass
class FileChunk:
    path: str
    content: str
    language: str


def _detect_language(path: Path) -> str:
    ext_map = {
        ".py": "python", ".go": "golang", ".ts": "typescript",
        ".tsx": "typescript", ".js": "javascript", ".jsx": "javascript",
        ".java": "java", ".scala": "scala", ".sql": "sql",
        ".sh": "bash", ".yaml": "yaml", ".yml": "yaml",
        ".tf": "terraform", ".json": "json", ".toml": "toml",
    }
    return ext_map.get(path.suffix.lower(), "text")


def _file_priority(path: Path) -> int:
    name = path.stem.lower()
    for keyword, score in FILE_PRIORITY.items():
        if keyword in name:
            return score
    return 50


def _should_skip(path: Path) -> bool:
    name = path.name.lower()
    for pattern in SKIP_PATTERNS:
        if pattern.startswith("*"):
            if name.endswith(pattern[1:]):
                return True
        elif name == pattern:
            return True
    return False


def _strip_python_comments(source: str) -> str:
    """Remove comments and docstrings from Python source to reduce tokens."""
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        result = []
        prev_toktype = tokenize.INDENT
        last_lineno = -1
        last_col = 0

        for tok_type, tok_string, tok_start, tok_end, _ in tokens:
            if tok_type == tokenize.COMMENT:
                continue
            if tok_type == tokenize.STRING:
                # Only strip if it's a standalone expression (docstring)
                if prev_toktype in (tokenize.INDENT, tokenize.NEWLINE, tokenize.NL):
                    continue
            if tok_start[0] > last_lineno:
                last_col = 0
            col_offset = tok_start[1] - last_col
            if col_offset > 0:
                result.append(" " * col_offset)
            result.append(tok_string)
            last_lineno, last_col = tok_end
            prev_toktype = tok_type

        return "".join(result)
    except tokenize.TokenizeError:
        return source  # return original if parsing fails


def _strip_c_style_comments(source: str) -> str:
    """Strips // line comments and /* block */ comments. Covers Go, JS, TS, Java, Scala."""
    source = re.sub(r'/\*.*?\*/', '', source, flags=re.DOTALL)
    source = re.sub(r'//[^\n]*', '', source)
    return source


def _strip_hash_comments(source: str) -> str:
    """Strips # line comments. Covers Bash, YAML, TOML, Terraform."""
    return re.sub(r'(?m)^\s*#[^\n]*\n?', '\n', source)


def _strip_sql_comments(source: str) -> str:
    """Strips -- line comments and /* block */ comments from SQL."""
    source = re.sub(r'/\*.*?\*/', '', source, flags=re.DOTALL)
    source = re.sub(r'--[^\n]*', '', source)
    return source


def _strip_comments(source: str, lang: str) -> str:
    if lang == "python":
        return _strip_python_comments(source)
    if lang in ("golang", "javascript", "typescript", "java", "scala"):
        return _strip_c_style_comments(source)
    if lang in ("bash", "yaml", "terraform", "toml"):
        return _strip_hash_comments(source)
    if lang == "sql":
        return _strip_sql_comments(source)
    return source


def _collect_files(root: Path, smart: bool = False) -> list[Path]:
    files = []
    if root.is_file():
        return [root]
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            fpath = Path(dirpath) / fname
            if fpath.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            if smart and _should_skip(fpath):
                continue
            if smart and _file_priority(fpath) <= 10:
                continue  # skip test/mock files in smart mode
            files.append(fpath)

    # Sort by priority descending so high-risk files are reviewed first
    return sorted(files, key=lambda p: -_file_priority(p))


def load_chunks(
    target: str,
    base_dir: str | None = None,
    provider: str = "anthropic",
    smart: bool = False,
) -> list[FileChunk]:
    """
    Load and chunk files from a path.

    smart=True: skip test files, strip comments/docstrings, prioritise
    high-risk files (auth, pipeline, API). Reduces token usage by ~40%.
    """
    chunk_limit = get_chunk_limit(provider)
    root = Path(target).resolve()
    base = Path(base_dir).resolve() if base_dir else root if root.is_dir() else root.parent

    files = _collect_files(root, smart=smart)
    if not files:
        return []

    chunks: list[FileChunk] = []
    batch_content = ""
    batch_paths: list[str] = []

    def flush_batch():
        if batch_content:
            chunks.append(FileChunk(
                path=", ".join(batch_paths),
                content=batch_content,
                language="mixed",
            ))

    for fpath in files:
        try:
            raw = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        rel = str(fpath.relative_to(base))
        lang = _detect_language(fpath)

        if smart:
            raw = _strip_comments(raw, lang)

        annotated = f"### File: {rel}\n```{lang}\n{raw}\n```\n\n"

        if len(annotated) > chunk_limit:
            flush_batch()
            batch_content = ""
            batch_paths = []
            for i in range(0, len(annotated), chunk_limit):
                part = annotated[i:i + chunk_limit]
                chunks.append(FileChunk(path=rel, content=part, language=lang))
            continue

        if batch_content and len(batch_content) + len(annotated) > chunk_limit:
            flush_batch()
            batch_content = ""
            batch_paths = []

        batch_content += annotated
        batch_paths.append(rel)

    flush_batch()
    return chunks


def load_diff_chunks(
    target: str,
    base_ref: str = "HEAD~1",
    provider: str = "anthropic",
) -> list[FileChunk]:
    """
    Review only what changed — diffs target against base_ref (default: last commit).
    Returns FileChunk objects containing the git diff for each changed file.

    Examples:
        load_diff_chunks(".", base_ref="HEAD~1")   # last commit
        load_diff_chunks(".", base_ref="main")      # vs main branch
    """
    try:
        import git
    except ImportError:
        raise RuntimeError("gitpython is not installed. Run: python -m pip install gitpython")

    chunk_limit = get_chunk_limit(provider)

    try:
        repo = git.Repo(target, search_parent_directories=True)
    except git.InvalidGitRepositoryError:
        raise ValueError(f"Not a git repository: {target}")

    try:
        diff = repo.git.diff(base_ref, "--", unified=5)
    except git.GitCommandError as e:
        raise ValueError(f"git diff failed: {e}")

    if not diff.strip():
        return []

    # Split diff into per-file sections
    file_diffs: dict[str, str] = {}
    current_file = None
    current_lines: list[str] = []

    for line in diff.splitlines(keepends=True):
        if line.startswith("diff --git "):
            if current_file and current_lines:
                file_diffs[current_file] = "".join(current_lines)
            # Extract filename: "diff --git a/foo.py b/foo.py" → "foo.py"
            parts = line.split(" b/", 1)
            current_file = parts[1].strip() if len(parts) > 1 else line
            current_lines = [line]
        elif current_file:
            current_lines.append(line)

    if current_file and current_lines:
        file_diffs[current_file] = "".join(current_lines)

    chunks: list[FileChunk] = []
    batch_content = ""
    batch_paths: list[str] = []

    def flush_batch():
        if batch_content:
            chunks.append(FileChunk(path=", ".join(batch_paths), content=batch_content, language="diff"))

    for filepath, file_diff in file_diffs.items():
        ext = Path(filepath).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            continue

        lang = _detect_language(Path(filepath))
        annotated = f"### Changed file: {filepath}\n```diff\n{file_diff}\n```\n\n"

        if len(annotated) > chunk_limit:
            flush_batch()
            batch_content = ""
            batch_paths = []
            for i in range(0, len(annotated), chunk_limit):
                chunks.append(FileChunk(path=filepath, content=annotated[i:i + chunk_limit], language=lang))
            continue

        if batch_content and len(batch_content) + len(annotated) > chunk_limit:
            flush_batch()
            batch_content = ""
            batch_paths = []

        batch_content += annotated
        batch_paths.append(filepath)

    flush_batch()
    return chunks
