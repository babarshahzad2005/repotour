# Ownership comes from changed lines in git log, not git blame

The original vision (`docs/design/vision.md`) mentioned `git blame` for ownership. We use changed lines from a single `git log --numstat` pass instead. Running blame on every file of a repo with about 1M lines would not fit the 2-minute performance target. Blame also answers a different question ("who wrote the lines that are there now"). For the newcomer's question, "who should I ask?", the better signal is "who has changed this area most". Changed lines are also easy to store per commit and update incrementally, which blame is not.

## Considered Options

- **`git blame` on every file:** most precise for current authorship, but too slow at scale and can't be updated incrementally.
- **Blame on a sample of files:** fast enough, but the results depend on the sample and are harder to explain as evidence.
