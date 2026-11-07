# Cache lives in the git common dir, not at the repo root

The original architecture put the cache in `.repotour-cache/` at the repo root. That folder would show up as untracked in `git status` in every user's repo, unless each user added it to `.gitignore`. Instead, the cache lives in `<git common dir>/repotour-cache/`, the shared `.git` directory that `git rev-parse --git-common-dir` returns. Git never tracks it, nothing needs adding to `.gitignore`, worktrees share it, and deleting it is still safe. The GitHub Action caches that path.

## Consequences

- Deleting the clone deletes the cache. That's fine, because the cache belongs to the clone.
- `--no-cache` still skips reading and writing the cache entirely.
