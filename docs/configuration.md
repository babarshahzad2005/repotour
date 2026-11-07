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
  base_url: http://localhost:11434/v1   # any OpenAI-compatible endpoint
  model: qwen2.5-coder:3b
  max_files: 15
```

Some settings are read by features that are still being built. They are validated now so the file format stays stable.
