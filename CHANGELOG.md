# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `repotour` command that writes `TOUR.md` with the tour's metadata (repository name, HEAD commit, tool version), as deterministic UTF-8 with LF line endings on every platform.
- `--out` option to write the tour to another path.
- Exit code 1 with a clear message when the path is not inside a git repository, git is missing or older than 2.30, or the repository has no commits.
- Any directory inside a repository tours the whole repository.
- A shallow clone produces the tour with a "history truncated" warning.
- The CLI notes when uncommitted changes are ignored; the tour always describes HEAD.
- Contributor documentation, code of conduct, security policy, and issue and pull request templates.
