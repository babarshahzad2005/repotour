# Configuration

Repotour reads an optional `.repotour.yml` at the repository root. Without one, every setting uses its default.

The file is strict: `version: 1` is required, and an unknown key or a wrong type stops the run with exit code `2` and names the offending key. That way a typo such as `exlude:` never fails silently.

CLI flags override the file. The effective configuration is hashed, and the first 12 characters of that hash appear in the tour, so you can tell which settings produced it.

## Full example with defaults

```yaml
version: 1                    # required

name: null                    # repository name shown in the tour (default: folder name)
since: 6m                     # hotspot window: <n><d|w|m|y>, 1m = 30 days,
                              # measured back from HEAD's commit date (--since overrides)

exclude: []                   # extra paths or globs to treat as vendored/excluded
pinned_entry_points: []       # files that always come first in the reading order
notes: {}                     # path -> hand-written note shown next to that path
test_patterns: []             # extra globs that mark files as tests
bots: []                      # author names to exclude, besides names ending in [bot]
ignore_revs: []               # commits to treat as bulk, besides .git-blame-ignore-revs
full_graph: false             # draw every module instead of collapsing (--full-graph)

thresholds:
  bulk_commit_files: 200      # commits touching more files are bulk commits
  bus_factor_share: 0.8       # top-author share that triggers a bus-factor warning
  bus_factor_min_files: 5     # ...only in directories with at least this many files
  bus_factor_min_commits: 10  # ...and at least this many non-bulk commits
  ownership_max_depth: 2      # deepest directory level that gets an ownership entry
  ownership_min_files: 5      # minimum source/test files for an ownership entry
  contact_window: 12m         # a contact must have committed within this window
  stable_window: 12m          # no change within this window marks an area stable
  graph_max_nodes: 60         # larger dependency graphs collapse to directories
  core_module_share: 0.1      # top share of modules by PageRank marked as core

caps:
  hotspots: 10
  authors_per_directory: 3
  entry_points_per_kind: 10
  reading_order: 5

summaries:                    # used only with --summaries
  provider: groq              # groq | openrouter | ollama | custom
  model: null                 # null: the provider's default model
  base_url: null              # null: the provider's endpoint; required for custom
  max_files: 15               # reading-order files first, then core modules
```

## AI summaries

`repotour --summaries` adds a short paragraph about each key file, written by an AI model, in a section labelled as AI-generated. It is off by default, and without the flag Repotour never uses the network.

| Provider | Endpoint | Default model | API key variable |
|---|---|---|---|
| `groq` (default) | `https://api.groq.com/openai/v1` | `qwen/qwen3.8-27b` | `GROQ_API_KEY` |
| `openrouter` | `https://openrouter.ai/api/v1` | none: set `model` | `OPENROUTER_API_KEY` |
| `ollama` | `http://localhost:11434/v1` | `qwen2.5-coder:3b` | none needed |
| `custom` | set `base_url` | none: set `model` | `REPOTOUR_LLM_API_KEY`, if the endpoint needs one |

- **Your key, your account.** Repotour ships no key. It reads `REPOTOUR_LLM_API_KEY` if set, otherwise the provider's own variable. Set it in your shell or CI secrets, never in `.repotour.yml`. Groq and OpenRouter both offer free tiers; Ollama runs models on your own machine.
- **What is sent.** Only the selected files (at most `max_files`), each trimmed to about 2,000 tokens. Before anything is sent, Repotour prints the files, the endpoint, and the model to stderr.
- **Cost.** Summaries are cached by file content, model, and prompt version, so an unchanged file is never sent twice.
- **Rate limits.** Free tiers limit requests per minute. When the provider answers "too many requests", Repotour waits as long as it asks (10 seconds if it does not say) and retries, up to 5 minutes in total per run. On Groq's free tier (8,000 tokens per minute) a full run of 15 files usually finishes within that. After that, the remaining files are skipped with one warning; run again later, and only those files are sent.
- **Failures.** A missing key, an error, or an unreachable endpoint becomes a warning; the tour is always written.

Any OpenAI-compatible server works with `custom`, for example LM Studio or llama.cpp:

```yaml
summaries:
  provider: custom
  base_url: http://localhost:1234/v1
  model: qwen2.5-coder-7b-instruct
```
