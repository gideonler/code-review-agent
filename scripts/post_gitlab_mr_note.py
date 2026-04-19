#!/usr/bin/env python3
"""
Post or update a single merge request note with the review markdown (GitLab API).

Designed for GitLab CI. Authentication (first match wins):
  - GITLAB_TOKEN: project access token or PAT (header PRIVATE-TOKEN)
  - else CI_JOB_TOKEN (header JOB-TOKEN) when the job is allowed to call the API

Required CI variables: CI_API_V4_URL, CI_PROJECT_ID, CI_MERGE_REQUEST_IID

Usage:
  python scripts/post_gitlab_mr_note.py [path/to/review.md]
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

_MARKER = "<!-- sentinel-gitlab -->"


def _request(method: str, url: str, headers: dict, data: bytes | None = None) -> tuple[int, str]:
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        raise RuntimeError(f"HTTP {e.code} {method} {url}: {body}") from e


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "review.md"
    if not os.path.isfile(path):
        print(f"post_gitlab_mr_note: file not found: {path}", file=sys.stderr)
        return 1

    with open(path, encoding="utf-8") as f:
        raw_md = f.read()
    body = raw_md.rstrip() + "\n\n" + _MARKER + "\n"

    base = os.environ.get("CI_API_V4_URL", "").rstrip("/")
    project_id = os.environ.get("CI_PROJECT_ID", "")
    mriid = os.environ.get("CI_MERGE_REQUEST_IID", "")
    if not base or not project_id or not mriid:
        print(
            "post_gitlab_mr_note: missing CI_API_V4_URL, CI_PROJECT_ID, or CI_MERGE_REQUEST_IID",
            file=sys.stderr,
        )
        return 1

    pat = os.environ.get("GITLAB_TOKEN", "").strip()
    job_tok = os.environ.get("CI_JOB_TOKEN", "").strip()
    if pat:
        auth_header = ("PRIVATE-TOKEN", pat)
    elif job_tok:
        auth_header = ("JOB-TOKEN", job_tok)
    else:
        print(
            "post_gitlab_mr_note: set GITLAB_TOKEN or rely on CI_JOB_TOKEN in GitLab CI",
            file=sys.stderr,
        )
        return 1

    enc_project = urllib.parse.quote(str(project_id), safe="")
    list_url = f"{base}/projects/{enc_project}/merge_requests/{mriid}/notes?per_page=100"
    headers = {auth_header[0]: auth_header[1], "Content-Type": "application/json"}

    _, raw = _request("GET", list_url, headers)
    notes = json.loads(raw)
    existing_id = None
    for n in notes:
        if _MARKER in (n.get("body") or ""):
            existing_id = n.get("id")
            break

    payload = json.dumps({"body": body}, ensure_ascii=False).encode("utf-8")

    if existing_id:
        note_url = f"{base}/projects/{enc_project}/merge_requests/{mriid}/notes/{existing_id}"
        _request("PUT", note_url, headers, payload)
        print(f"post_gitlab_mr_note: updated note #{existing_id}")
    else:
        create_url = f"{base}/projects/{enc_project}/merge_requests/{mriid}/notes"
        _request("POST", create_url, headers, payload)
        print("post_gitlab_mr_note: posted new note")

    return 0


if __name__ == "__main__":
    sys.exit(main())
