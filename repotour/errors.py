"""Errors that stop a run. Each carries the exit code the CLI reports."""

from __future__ import annotations


class RepotourError(Exception):
    exit_code: int = 1


class RepositoryError(RepotourError):
    """Not a usable repository: not a git repo, git missing or too old, or no commits."""

    exit_code = 1
