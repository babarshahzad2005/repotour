# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Start here: up to five files to read first, in order. Pinned entry points come first, then execution entry points, then public surfaces; within each group files rank by PageRank and hotspot percentiles. After the first entry point, each next file is the best one imported by a file already chosen. Every reason comes from real signals (entry point, imported by, importer count, repeated changes), and the list is never padded.
- Go in the dependency graph and entry points: imports resolve through every `go.mod` module path (covering `go.work` workspaces), linking to one representative file of the imported package (ADR-0005); files of an imported package are never called leaf modules. Entry points: `package main` programs, `ListenAndServe` servers, and each module's root package.
- JavaScript and TypeScript in the dependency graph and entry points: static `import`/`export ... from`/`require('literal')` (and TypeScript `import x = require()`), resolved through relative paths with extension inference and index files, `tsconfig.json` `paths`/`baseUrl`, and workspace packages; entry points from `package.json` `main`/`module`/`exports`/`bin`, server startup (`.listen()`), and `require.main === module`.
- Core and leaf modules: Repotour's own deterministic PageRank names the most depended-on modules; modules nothing imports (that are not entry points or empty) are listed as safe places for a first change.
- Large dependency graphs collapse to directories, one level coarser at a time, to at most `thresholds.graph_max_nodes` (60) nodes; if even the top level is too big, the highest-ranked directories are kept and the rest counted. `--full-graph` (or `full_graph: true`) draws every module.
- Per-file parse cache: parse results are cached by content hash and language adapter version, so a re-run parses only changed files (a moved but unchanged file is never re-parsed). Within one run, each file is parsed once and shared by all analyzers.
- Entry points section: where execution starts (scripts, CLIs, servers, web apps, `python -m` modules, console scripts) and the public surface (top-level packages), plus commands from `package.json`, `Dockerfile`, and `Cargo.toml` that point at real files, in any language. Pinned entry points from config come first; each kind is capped at 10.
- Dependency graph section (Python): static imports parsed with tree-sitter and resolved to repository files (relative imports, top-level packages, `src/` layout), rendered as a Mermaid diagram that displays on GitHub. Every edge cites its import; external modules are counted; test, generated, and vendored files are left out; unparseable files become warnings.

## [0.2.0] - 2026-11-07

Second milestone (M2): history and ownership.

### Added

- Hotspots section: the files changed most often in the hotspot window, measured back from HEAD's commit date (`--since`, default 6 months), each citing its commit range. Merge commits, generated and vendored files, and files no longer tracked are left out.
- Ownership section: for directories up to depth 2 with at least 5 source or test files, the top authors by share of changed lines (names only, never emails) and contacts who committed there in the 12 months before HEAD. Authors are merged only through `.mailmap`; bots (`[bot]` names and config `bots`) and bulk commits are left out; renamed files count toward their current directory.
- Bus-factor warnings in the Ownership section when one author made more than 80% of a directory's changes and it has at least 5 files and 10 commits (all configurable). Each directory is marked active (changed inside the hotspot window) or stable (no change in 12 months).
- Incremental history: the cache keeps the last toured commit's history, so after pulling only the new commits are read from git; rewritten history is read in full, and changing `--since` never re-reads git. History is kept in one canonical order, so incremental and cold runs give identical tours.
- Bulk commits (more files than `thresholds.bulk_commit_files`, default 200, or listed in `.git-blame-ignore-revs` or config `ignore_revs`) are left out of the history-based sections, and the tour says how many with examples.
- Renamed and moved files keep their history: renames are detected in the same `git log` pass and chained to the path at HEAD.
- `python -m repotour` entry point.
- Benchmarks on Flask and fzf at pinned commits, run weekly in CI (median of three cold runs: 0.69 s and 1.09 s against a 10 s target).

## [0.1.0] - 2026-11-07

First milestone (M1): the CLI skeleton and the overview section.

### Fixed

- A top-level directory that holds only submodules is summarized as such instead of "0 files".
- Generated-file headers only count inside a comment at the start of a line, so prose that mentions the marker is no longer misclassified.

### Added

- `repotour` command that writes `TOUR.md` with the tour's metadata (repository name, HEAD commit, tool version), as deterministic UTF-8 with LF line endings on every platform.
- `--out` option to write the tour to another path.
- Exit code 1 with a clear message when the path is not inside a git repository, git is missing or older than 2.30, or the repository has no commits.
- Any directory inside a repository tours the whole repository.
- A shallow clone produces the tour with a "history truncated" warning.
- The CLI notes when uncommitted changes are ignored; the tour always describes HEAD.
- `.repotour.yml` configuration: `version: 1` required, unknown keys and wrong types exit 2 naming the key, optional `name:` override, and the config hash shown in the tour. See `docs/configuration.md`.
- `--since` option for the hotspot window, overriding the config file.
- Generated tours start with a `<!-- generated by repotour -->` marker; an existing file without it is never overwritten (exit 4) unless `--force` is given.
- Warnings render in a closing Warnings section and are counted in the CLI summary; `--strict` exits 3 when any warning was produced.
- Overview section: repository size and a language breakdown, each language citing its largest files. Content is read from the commit, never the working tree.
- Analyzer pipeline: analyzers run in dependency order; a failing analyzer becomes a warning and an unavailable section instead of stopping the run.
- File classification: generated and vendored files (from `.gitattributes`, well-known paths, lockfiles, generated-file headers, and config `exclude`) are left out of languages and size and listed with their reasons. Tests are recognized by directory, file name, and config `test_patterns`.
- Binary files and files over 1 MB are skipped; unexpected ones are reported as warnings. Git LFS pointers count as other files; submodules are listed but never entered.
- Analysis cache in the git common directory (shared by worktrees, never tracked, safe to delete): re-running on the same commit and config renders without re-scanning. `--no-cache` neither reads nor writes it.
- Project types (web app, library, CLI, monorepo) detected from manifests and build files, each with evidence, or "unknown". Monorepo packages from npm/pnpm workspaces, `go.work`, Cargo workspaces, or manifests in several top-level directories.
- "How to work on it": install, run, and test commands quoted from Makefile/justfile targets, package.json scripts, pyproject task runners, tox, nox, and GitHub Actions steps, each citing its source; the highest-priority source wins per purpose, and the tour says so when none are found.
- Top-level directories with a one-line purpose, taken from a config note, the directory's README, a table of well-known names, or a summary of its files, and showing where each came from. Notes on other paths render as maintainer notes; a note for a missing path is a warning.
- Missing basics: the overview flags a missing README, tests, contributing guide, license, or CI configuration, saying what was looked for.
- Contributor documentation, code of conduct, security policy, and issue and pull request templates.

[Unreleased]: https://github.com/babarshahzad2005/repotour/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/babarshahzad2005/repotour/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/babarshahzad2005/repotour/releases/tag/v0.1.0
