# Contributing to Repotour

Thanks for your interest in improving Repotour. This guide covers setup, the development loop, and how changes get merged.

## Before you start

- Read the [vision](docs/design/vision.md) and [architecture](docs/design/architecture.md). The architecture's "Rules every change must follow" section is binding.
- Use the project's vocabulary from the [glossary](GLOSSARY.md) in code, tests, and docs.
- Check the [architecture decision records](docs/adr/) before changing anything they cover. To reverse a decision, propose a new ADR.
- For anything bigger than a small fix, open an issue first so we can agree on the approach.

## Setup

Requirements: Python 3.11+, git 2.30+, and [uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/babarshahzad2005/repotour.git
cd repotour
uv sync
uv run pre-commit install
```

## Development loop

```sh
uv run pytest            # tests
uv run ruff check        # lint
uv run ruff format       # format
uv run mypy              # type-check (strict)
uv run repotour          # run the CLI on the current repository
```

The pre-commit hooks run ruff and mypy on every commit.

### Tests

- Write the test first. Behavior is tested through fixture repositories with scripted history (see `tests/fixtures/`), never against real-world repositories.
- New behavior gets a fixture-repository test and, if the tour output changes, an updated golden tour.
- To update golden tours after an intentional output change, run `uv run pytest --update-goldens` and review the diff in `tests/golden/` carefully. It is part of your change.
- Output must stay deterministic: sort everything, break ties by path, and never add timestamps.

## Commits and pull requests

- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`, `ci:`.
- One topic per pull request, on a short-lived branch from `main`.
- `main` is protected. Pull requests merge by squash once CI passes on Linux, macOS, and Windows.
- Add a line to the `Unreleased` section of [CHANGELOG.md](CHANGELOG.md) for user-visible changes.

## Reporting bugs and security issues

- Bugs and feature requests: use the [issue templates](https://github.com/babarshahzad2005/repotour/issues/new/choose).
- Security vulnerabilities: do not open a public issue. See [SECURITY.md](SECURITY.md).

## Code of conduct

Participation in this project is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).
