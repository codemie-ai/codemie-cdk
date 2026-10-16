# CodeMie CDK

Infrastructure as code for the CodeMie platform. Manage assistants, datasources and workflows with declarative YAML files.

This repository holds two packages. Each one has its own README with usage and examples.

| Package | Path | Language | Registry |
|---------|------|----------|----------|
| [`@codemieai/cdk`](iac/codemie-iac-nodejs/README.md) | `iac/codemie-iac-nodejs` | TypeScript (Node.js 22 or later) | npm |
| [`codemie-iac-python`](iac/codemie-iac-python/README.md) | `iac/codemie-iac-python` | Python 3.12 or later | not published yet |

The Node.js package is the `codemie` command. It deploys the YAML files to the platform. The Python package is a library that turns platform resources into YAML documents and reads them back. It has no command line tool and does not call the platform.

```bash
npm install --save-dev @codemieai/cdk
```

## Requirements

- Node.js 22 or later (`@codemieai/cdk`)
- `codemie-sdk` `>=0.1.0 <1.0.0` for `@codemieai/cdk` (installed as a dependency)
- Python 3.12 or later (`codemie-iac-python`)

## Related repositories

- [codemie-mcp-servers](https://github.com/codemie-ai/codemie-mcp-servers): MCP servers that give AI tools access to CodeMie.

## Contributing

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md) first.

## Security

Do not report vulnerabilities in public issues. Follow [SECURITY.md](SECURITY.md).

For bugs and feature requests, use [GitHub Issues](https://github.com/codemie-ai/codemie-cdk/issues).

## Releasing

See [docs/RELEASING.md](docs/RELEASING.md).

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).
