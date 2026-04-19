"""
Extracts git metadata from the repo containing a given path.
Used to stamp audit records with commit hash, branch, and author.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class GitMeta:
    branch: str | None
    commit: str | None
    author: str | None
    repo_root: str | None


def get_git_meta(target: str) -> GitMeta:
    try:
        import git
        repo = git.Repo(target, search_parent_directories=True)
        try:
            branch = repo.active_branch.name
        except TypeError:
            branch = "detached"

        commit = repo.head.commit.hexsha[:12]
        author = repo.head.commit.author.name
        root = repo.working_tree_dir
        return GitMeta(branch=branch, commit=commit, author=author, repo_root=root)
    except Exception:
        return GitMeta(branch=None, commit=None, author=None, repo_root=None)
