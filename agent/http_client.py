"""
Shared httpx client for LLM providers so HTTP_PROXY / HTTPS_PROXY / NO_PROXY
from the environment are honoured (corporate runners, GitLab CI variables).
"""

import httpx

# Reviews can be slow on large diffs; connect may wait on TLS through a proxy.
DEFAULT_TIMEOUT = httpx.Timeout(300.0, connect=120.0)


def llm_http_client() -> httpx.Client:
    """httpx client with trust_env=True (reads proxy vars from the environment)."""
    return httpx.Client(timeout=DEFAULT_TIMEOUT, trust_env=True)
