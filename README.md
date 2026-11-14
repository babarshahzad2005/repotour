# Repotour

> Status: in design. Not yet usable.

Repotour is a CLI that analyzes a git repository and writes a tour for someone seeing it for the first time: where to start reading, what matters, and who to ask. Every claim in the tour points to its evidence.

## Documentation

- [Vision](docs/design/vision.md): what Repotour does and does not do
- [Architecture](docs/design/architecture.md): components, data contracts, and rules
- [Flows](docs/design/flows.md): step-by-step behavior and error handling
- [Configuration](docs/configuration.md): the `.repotour.yml` reference
- [JSON output](docs/json.md): the experimental `--json` format
- [GitHub Action](docs/action.md): keep the tour current on every release
- [Glossary](GLOSSARY.md): the project's vocabulary
- [Architecture decision records](docs/adr/)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Please follow the [Code of Conduct](CODE_OF_CONDUCT.md), and report security issues as described in [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE)
