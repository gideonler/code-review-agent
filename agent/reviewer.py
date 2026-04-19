"""
Orchestrates the review: loads files, calls the provider, streams results,
and persists every completed review to the audit store.
"""

from pathlib import Path

from agent.chunker import FileChunk, load_chunks, load_diff_chunks
from agent.providers.base import LLMProvider
from agent.providers.factory import get_provider


def _load_system_prompt() -> str:
    claude_md = Path(__file__).parent.parent / "CLAUDE.md"
    if not claude_md.exists():
        raise FileNotFoundError(f"CLAUDE.md not found at {claude_md}")
    return claude_md.read_text(encoding="utf-8")


def review_target(
    target: str,
    stream: bool = False,
    provider_name: str = "anthropic",
    api_key: str | None = None,
    smart: bool = False,
    save: bool = True,
    diff_ref: str | None = None,
):
    """
    Main entry point.
    - stream=False → returns (review_text, review_id)
    - stream=True  → returns a generator yielding (chunk_index, total_chunks, text_delta);
                     persists when the generator is fully consumed.
    save=False skips persisting to the audit store (useful for tests).
    """
    provider = get_provider(provider_name, api_key=api_key)
    system_prompt = _load_system_prompt()
    if diff_ref:
        chunks = load_diff_chunks(target, base_ref=diff_ref, provider=provider_name)
    else:
        chunks = load_chunks(target, provider=provider_name, smart=smart)

    if not chunks:
        msg = f"No reviewable files found at: {target}"
        if stream:
            return _empty_stream(msg)
        return msg, None

    if stream:
        return _review_stream(
            chunks=chunks,
            provider=provider,
            system_prompt=system_prompt,
            target=target,
            provider_name=provider_name,
            smart=smart,
            save=save,
        )

    all_reviews: list[str] = []
    for chunk in chunks:
        prior_context = _build_prior_context(all_reviews) if all_reviews else ""
        text = provider.review_chunk(chunk, system_prompt, prior_context)
        all_reviews.append(text)

    final_text = _merge_reviews(all_reviews, chunks)
    review_id = None
    if save:
        review_id = _persist(
            raw=final_text,
            target=target,
            provider_name=provider_name,
            smart=smart,
        )
    return final_text, review_id


def _empty_stream(msg: str):
    yield (0, 0, msg)


def _review_stream(
    chunks,
    provider: LLMProvider,
    system_prompt: str,
    target: str,
    provider_name: str,
    smart: bool,
    save: bool,
):
    total = len(chunks)
    all_reviews: list[str] = []
    for i, chunk in enumerate(chunks):
        prior_context = _build_prior_context(all_reviews) if all_reviews else ""
        chunk_text = ""
        for delta in provider.review_chunk_stream(chunk, system_prompt, prior_context):
            chunk_text += delta
            yield (i, total, delta)
        all_reviews.append(chunk_text)

    final_text = _merge_reviews(all_reviews, chunks)
    if save:
        _persist(
            raw=final_text,
            target=target,
            provider_name=provider_name,
            smart=smart,
        )


def _persist(raw: str, target: str, provider_name: str, smart: bool) -> int | None:
    try:
        from agent.parser import parse_review
        from agent.store import save_review
        from agent.git_meta import get_git_meta
        from agent.enricher import enrich_findings

        result = parse_review(raw)
        enrich_findings(result.findings)
        meta = get_git_meta(target)
        return save_review(
            result=result,
            target=target,
            provider=provider_name,
            smart_mode=smart,
            git_branch=meta.branch,
            git_commit=meta.commit,
            git_author=meta.author,
        )
    except Exception:
        return None


def _build_prior_context(reviews: list[str]) -> str:
    parts = []
    for r in reviews:
        start = r.find("FINDINGS")
        end = r.find("POSITIVE NOTES")
        if start != -1 and end != -1:
            parts.append(r[start:end].strip())
        elif start != -1:
            parts.append(r[start:].strip())
    return "\n\n".join(parts)


def _merge_reviews(reviews: list[str], chunks: list[FileChunk]) -> str:
    if len(reviews) == 1:
        return reviews[0]
    merged = "# Aggregated Code Review\n\n"
    merged += f"_Reviewed {len(chunks)} file chunks._\n\n---\n\n"
    for i, (review, chunk) in enumerate(zip(reviews, chunks), 1):
        merged += f"## Chunk {i}: {chunk.path}\n\n{review}\n\n---\n\n"
    return merged
