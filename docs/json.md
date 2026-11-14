# JSON output (experimental)

`repotour --json FILE` writes the tour model as JSON in addition to the normal tour. Use it when a tool, not a person, reads the tour: dashboards, bots, or checks in CI.

> **Experimental.** The shape may change in any minor release until it is marked stable. Check `schema_version` before reading anything else.

## Shape

```json
{
  "generator": "repotour",
  "schema_version": 1,
  "tour": {
    "meta": {"repo_name": "...", "head_commit": "...", "tool_version": "...", "config_hash": "..."},
    "overview": {...},
    "entry_points": {...},
    "reading_order": {...},
    "hotspots": {...},
    "ownership": {...},
    "dependency_graph": {...},
    "summaries": [],
    "unavailable": [],
    "warnings": []
  }
}
```

- `tour` holds the same sections as the Markdown tour, field for field. A section is `null` when it was not produced.
- `unavailable` names sections whose analyzer failed; their reason is in `warnings`.
- Every claim carries an `evidence` list. Each entry has a `kind` (for example `file`, `commit_range`, `import`, `config`), a `ref`, and an optional `detail`.
- Lists keep the order the tour shows them in. Object keys are sorted.

## Guarantees

- The same commit and configuration give byte-identical JSON on every platform: UTF-8, LF line endings, no timestamps.
- `generator` is always `"repotour"`. Repotour uses it to recognize its own files: an existing file at the `--json` path without it is never overwritten (exit code 4) unless `--force` is given. When either target is refused, neither file is written.
