# Repotour

[![CI](https://github.com/babarshahzad2005/repotour/actions/workflows/ci.yml/badge.svg)](https://github.com/babarshahzad2005/repotour/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/repotour)](https://pypi.org/project/repotour/)
[![Python](https://img.shields.io/pypi/pyversions/repotour)](https://pypi.org/project/repotour/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

Repotour reads a git repository and writes a tour for someone seeing it for the first time: what it is and how to run it, which five files to read first, what changes most, who to ask, and how the modules fit together. Every claim in the tour points to its evidence: a file, a line, an import, or a range of commits.

```console
$ pip install repotour
$ cd some-repository
$ repotour
Wrote /home/you/some-repository/TOUR.md (0 warnings)
```

**See real tours:** [Flask](docs/samples/flask.md) · [Express](docs/samples/express.md) · [fzf](docs/samples/fzf.md)

## What a tour contains

| Section | Answers | Built from |
|---|---|---|
| **Overview** | What is this, and how do I run it? | Languages and size (generated and vendored files left out), project type with evidence, install/run/test commands quoted from Makefiles, `package.json`, task runners, and CI, a purpose for each top-level directory, and missing basics such as tests or a license |
| **Start here** | Which files do I read first? | Up to five files in order: entry points first, then what they import, ranked by a PageRank of the import graph and recent change frequency. Each comes with its reason |
| **Entry points** | Where does execution start? | `main` programs, CLIs, servers, web apps, `python -m` modules, console scripts, and package entry points from manifests |
| **Hotspots** | What changes most? | Commits in the last six months (configurable), measured back from HEAD's date, with merge and bulk commits left out and renames followed |
| **Ownership** | Who do I ask? | Top authors per directory by changed lines, recent contacts, bus-factor warnings, and active versus stable areas; `.mailmap` respected, bots left out |
| **Dependency graph** | How do the modules fit together? | Static imports parsed with tree-sitter (Python, JavaScript/TypeScript, Go), drawn as a Mermaid diagram that renders on GitHub; core modules and safe first-change modules |
| **Key files, summarized by AI** | What does each key file do? | Optional, off by default; see [AI summaries](#ai-summaries) |

The same commit and settings always give a byte-identical tour, on Linux, macOS, and Windows.

## Install

Repotour needs Python 3.11 or newer and git 2.30 or newer.

```console
$ pip install repotour        # or: pipx install repotour, uv tool install repotour
```

## Usage

```console
$ repotour [PATH]             # any directory inside the repository; default: the current one
```

| Option | Effect |
|---|---|
| `--out FILE` | Write the tour somewhere else (default: `TOUR.md` at the repository root) |
| `--format md\|html` | Markdown, or one self-contained HTML page that works offline |
| `--json FILE` | Also write the tour as JSON for tools ([experimental format](docs/json.md)) |
| `--since 3m` | Hotspot window (`d`, `w`, `m` = 30 days, `y`) |
| `--full-graph` | Draw every module instead of collapsing large graphs to directories |
| `--summaries` | Add AI summaries of key files ([details](#ai-summaries)) |
| `--strict` | Exit with code 3 if anything produced a warning |
| `--force` | Overwrite an output file that Repotour did not write |
| `--no-cache` | Neither read nor write the analysis cache |

The tour always describes the committed HEAD; uncommitted changes are ignored. Repotour never overwrites a file it did not generate unless you pass `--force`.

Exit codes: `0` success · `1` not a git repository, git missing or too old, or no commits · `2` invalid `.repotour.yml` · `3` warnings with `--strict` · `4` the output file was not written by Repotour.

## Configuration

Everything works without configuration. To tune it, add `.repotour.yml` at the repository root:

```yaml
version: 1
exclude: ["legacy/**"]               # treat as vendored: left out of every section
pinned_entry_points: [cmd/server/main.go]
notes:
  internal/billing: Talks to the payment provider; ask the payments team first.
since: 3m
```

See the [configuration reference](docs/configuration.md) for every setting and its default. Unknown keys are an error, so typos never fail silently.

## AI summaries

`repotour --summaries` adds one short paragraph about each key file (the reading order, then the core modules, at most 15), in a section labelled as AI-generated. It is off by default, and without it Repotour never uses the network.

You bring your own provider and key; Repotour ships none:

| Provider | Setup |
|---|---|
| **Groq** (default; free tier) | Create a key at [console.groq.com](https://console.groq.com) and set `GROQ_API_KEY` |
| **OpenRouter** | Set `OPENROUTER_API_KEY` and choose a `model` in `.repotour.yml` |
| **Ollama** (runs on your machine) | `summaries: {provider: ollama}` |
| **Any OpenAI-compatible server** | `summaries: {provider: custom, base_url: ..., model: ...}` |

How it handles your code:

- Only the selected files are sent, each trimmed to about 2,000 tokens, to the provider you configured. Before sending, Repotour prints the files, the endpoint, and the model.
- Summaries are cached by file content and model, so an unchanged file is never sent twice.
- Rate limits are waited out (up to 5 minutes per run); errors and a missing key become warnings, and the tour is always written.

## GitHub Action

Keep the tour current with a pull request on every release:

```yaml
# .github/workflows/tour.yml
name: Codebase tour
on:
  release:
    types: [published]
  workflow_dispatch:
permissions:
  contents: write
  pull-requests: write
jobs:
  tour:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0
      - uses: babarshahzad2005/repotour@v1
```

Also enable **Settings > Actions > General > Allow GitHub Actions to create and approve pull requests**. Inputs, outputs, and AI summaries in CI are described in [docs/action.md](docs/action.md).

## Quality and performance

**Reading order.** Each sample tour's five "Start here" files are reviewed against a [written rubric](docs/rubric.md): a file passes if it is an entry point, a core module, or something an entry point imports directly, and its stated reason is true. Results: Flask 4/5, Express 4/5, fzf 5/5 ([review](docs/samples/REVIEW.md)).

**Robustness.** Every week CI tours 20 real repositories pinned to exact commits, including Django, Caddy, Prettier, Vue's pnpm monorepo, heavy vendoring and migrations, a Rust repository, and a shallow clone. None may crash ([corpus](tests/corpus.yml)).

**Speed.** First run with an empty cache, and a re-run after the next release with the cache from the previous one. Median of 3 runs on a standard GitHub Actions `ubuntu-latest` runner, at pinned commits ([method](benchmarks/run.py)):

| Repository | Size | First run | Re-run after a release | Target |
|---|---|---:|---:|---|
| [pallets/flask](https://github.com/pallets/flask) 3.1.3 | 5,600 commits | 1.0 s | 0.4 s (from 3.1.2) | first < 10 s, re-run < 5 s |
| [junegunn/fzf](https://github.com/junegunn/fzf) v0.75.0 | 40,000 lines | 1.5 s | 0.6 s (from v0.74.0) | first < 10 s, re-run < 5 s |
| [golang/go](https://github.com/golang/go) go1.27.3 | 68,000 commits, 1.7M lines | 45 s | 4.8 s (from go1.27.0) | first < 2 min, re-run < 5 s |
| [kubernetes/kubernetes](https://github.com/kubernetes/kubernetes) v1.37.2 | 143,000 commits, 3M lines | 121 s | | stretch target, reported only |

The benchmarks run weekly in CI; each run's results are in the [Benchmarks workflow](https://github.com/babarshahzad2005/repotour/actions/workflows/benchmarks.yml) summary.

## How it works

Repotour reads the repository through the `git` CLI and works only from what is committed. Analyzers run in dependency order over one snapshot of HEAD: an overview, entry points, history, ownership, the dependency graph, and the reading order. Each produces evidence-backed claims into one tour model, which renders to Markdown, HTML, or JSON. Results are cached in `.git/repotour-cache` per analyzer, commit, and settings; parsed files are cached by content, and history is read incrementally, so a re-run reads only new commits and changed files. The cache is never tracked and safe to delete.

More detail: [vision](docs/design/vision.md) · [architecture](docs/design/architecture.md) · [flows](docs/design/flows.md) · [glossary](GLOSSARY.md) · [decision records](docs/adr/)

## Limitations

- The dependency graph and reading order cover Python, JavaScript/TypeScript, and Go. Other languages still get the overview, entry points from manifests, hotspots, and ownership.
- Imports are read statically; dynamic imports and runtime plugin loading are not followed.
- Ownership measures changed lines in history, which is not the same as who understands the code best. Treat it as a hint about whom to ask.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Please follow the [Code of Conduct](CODE_OF_CONDUCT.md), and report security issues as described in [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE)
