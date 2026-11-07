# Repotour

Repotour turns a git repository into a tour: a guide for someone seeing the codebase for the first time. This glossary fixes the words the tour, the code, and the docs use for its concepts.

## The tour

**Tour**:
The single document Repotour produces for one repository at one commit. It covers the whole repository, never a subfolder or a single package.
_Avoid_: report, guide, summary, docs

**Claim**:
Any statement in the tour about the repository, such as "this is an entry point" or "Alice owns `api/`". Every claim carries evidence.
_Avoid_: finding, insight, fact

**Evidence**:
The pointer that backs a claim: a file path, a commit range, an import, a config entry, or a git attribute.
_Avoid_: source, proof, citation

**Directory purpose**:
The one-line description of a top-level directory in the overview. It is taken from a hand-written note, the directory's own README, or a well-known directory name, and otherwise falls back to a description of what the directory contains. It is never guessed.
_Avoid_: directory summary, description

## Code structure

**Project type**:
What kind of project the repository is: web app, library, CLI, or monorepo. A repository can have several types at once, each backed by evidence, or be "unknown".
_Avoid_: kind, category, archetype

**Generated file** / **Vendored file**:
A file the project's own contributors did not write by hand: produced by a tool, or copied in from another project. Neither is a hotspot, counts toward ownership, or appears in the reading order.
_Avoid_: third-party file, build artifact

**Core module**:
A source module many others depend on, ranked by its centrality in the dependency graph, which excludes test files.
_Avoid_: central file, important module

**Leaf module**:
A source module nothing else imports and that is not an entry point. It is a safe place for a first change.
_Avoid_: safe file, isolated module

**Entry point**:
A file where a reader can enter the codebase. It comes in two kinds: an **execution entry point**, where running starts (a `main`, server startup, CLI definition, route table, or package script), and a **public surface**, what a library exposes to its users (a package's `__init__.py`, the `main`/`exports` target of `package.json`, or an importable Go package).
_Avoid_: main file, root file, starting point

## History

**History**:
The commits reachable from the tour's commit, excluding merge commits. Other branches are not part of history.
_Avoid_: git log, commit log, activity

**Hotspot window**:
The period of history that hotspots are counted over, measured back from the tour commit's date, not from today.
_Avoid_: time range, since period, lookback

**Bulk commit**:
A commit so broad it says nothing about who works on what, such as a formatting pass, a mass rename, or license headers. It is identified by size or by being listed as a commit to ignore. Bulk commits count toward neither hotspots nor ownership.
_Avoid_: noise commit, mass commit

**Hotspot**:
A file ranked by how many non-bulk commits changed it within the hotspot window.
_Avoid_: churn, hot file, high-activity file

**Ownership**:
Each author's share of the lines changed in a directory across history. It measures who has changed an area most, not who wrote the lines that exist today.
_Avoid_: authorship, blame, code owners

**Contact**:
An author the tour suggests asking about a directory: someone with a high ownership share and a commit to that directory in the last 12 months of history. Contacts are shown by name, never by email.
_Avoid_: owner, maintainer, expert

**Bus-factor warning**:
A warning that one author holds most of a directory's ownership, given only when the directory is big and busy enough for that to be a real risk.
_Avoid_: single point of failure, knowledge silo

**Active area** / **Stable area**:
A directory with a non-bulk change inside the hotspot window is active. A directory with no change in the 12 months before the tour commit is stable. A directory can be neither.
_Avoid_: hot / cold, live / dead

## Reading

**Reading order**:
The ordered list of five files the tour tells a newcomer to read first, each with a reason built from the signals that chose it.
_Avoid_: start-here list, recommended files, learning path
