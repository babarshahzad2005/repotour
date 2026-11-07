# What we're building

The idea behind Repotour, a codebase tour generator for new contributors.

- A CLI that analyzes any git repository and writes a guide for someone seeing it for the first time
- Point it at a repo, get back a readable tour: where to start, what matters, and who to ask
- A guide for humans, not a stats dump

## Core feature 1: The overview

- Detects languages, size, and project type (web app, library, CLI, monorepo) from files like `package.json`, `pyproject.toml`, `go.mod`, and `Dockerfile`
- Summarizes how to install, run, and test the project, quoting commands from build files, scripts, and CI config (never inventing them)
- Lists the top-level directories with a one-line purpose for each, taken from a config note, the directory's README, a well-known name, or its file mix
- Flags missing basics: no README, no tests, no contributing guide, no license, no CI configuration
- Leaves generated and vendored files out of every count, and lists them with the reason

## Core feature 2: Entry points and reading order

- Finds entry points: `main` functions, server startup files, CLI definitions, route tables, and `package.json` scripts
- "Start here" reading order: combines entry points, the dependency graph, and hotspots to suggest the five files to read first, in order
- Each suggested file gets a short note on why it's on the list
- Reading order is reproducible: same repo and same commit give the same tour

## Core feature 3: History, hotspots, and ownership

- Hotspots: files changed most often in a configurable window (default six months)
- Ownership: top contributors per directory from changed lines in commit history (see docs/adr/0002)
- Bus factor warnings: directories where one person wrote nearly everything
- Recently active areas vs. stable, rarely touched code
- Respects `.mailmap` so one person with several emails counts once

## Core feature 4: Dependency graph

- Module-level import graph built with tree-sitter, so one approach covers many languages
- v1 languages: Python, JavaScript/TypeScript, Go
- Rendered as Mermaid so it displays directly on GitHub
- Large graphs collapse to directory level, with the full graph available on request
- Highlights core modules (most depended on) and leaf modules (safe places for first changes)

## Core feature 5: Output and automation

- Outputs a single Markdown file or a self-contained HTML page
- Optional LLM summaries of key files, off by default, with results cached per file hash
- GitHub Action that regenerates the tour on each release and opens a PR with the update
- Config file (`.repotour.yml`) to exclude paths, pin entry points, and add hand-written notes

## Analysis has to be accurate on real repos

- Real repos are messy: generated code, vendored dependencies, lockfiles, and huge migrations are the normal case, not the edge case
- Generated and vendored files are detected and excluded from hotspots and ownership (via `.gitattributes`, common paths, and file headers)
- Bulk commits (formatting passes, renames, license headers) don't distort ownership; renames are followed via repo-wide rename detection (`git log -M`)
- Unparseable files are skipped with a warning instead of crashing the run
- Every claim in the tour points to its evidence: a file path, a commit range, or an import
- Why it matters: if the tour sends a newcomer to the wrong file once, they stop trusting it

## Caching and incremental runs

- Analysis results cached per commit, so re-running on the same commit is instant
- Incremental mode only re-analyzes files changed since the last cached commit
- LLM summaries cached by file content hash; unchanged files never cost another call
- Cache lives in a local directory and can be safely deleted

## Performance targets

Measured without LLM summaries on a standard GitHub Actions `ubuntu-latest` runner: median of 3 runs after one warm-up, Repotour cache empty, every repo pinned to a commit SHA.

- Medium: `pallets/flask` and `junegunn/fzf` each in under 10 seconds
- Large: `golang/go` (about 68k commits, 1.7M lines) in under 2 minutes
- Stretch, reported but not a release gate: `kubernetes/kubernetes`
- Incremental re-run after a typical release (up to 200 new commits, up to 5% of files changed) in under 5 seconds
- Benchmarks and the approach behind them written up in the README

## What we're NOT building (v1)

- A hosted web service or accounts (CLI and GitHub Action only)
- IDE extensions
- Languages beyond Python, JavaScript/TypeScript, and Go
- Code quality scoring or linting
- Interactive chat about the codebase
- Support for version control systems other than git

## End result

A working tool: install it with one command, run it on any repo, and get a tour with an overview, entry points, a "start here" reading order, hotspots, ownership, and a dependency graph that renders on GitHub, kept up to date by a GitHub Action, with published sample tours for Flask, Express, and fzf in the README.
