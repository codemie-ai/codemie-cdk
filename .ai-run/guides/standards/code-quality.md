# Code Quality

Rules only. Commands are in `.ai-run/guides/quality-gates.md`.

## Biome linter (`iac/codemie-iac-nodejs/biome.json`)

The config sets `recommended` to false and lists each rule. Read the file before you assume a rule applies.

| Avoid | Prefer | Rule |
|---|---|---|
| `console.log` | `logger` | `noConsole` |
| `any` in source | A real type or `unknown`. Test files may use `any` | `noExplicitAny` (off in the test override) |
| `if (x) return;` | A block with braces | `useBlockStatements` |
| `array.forEach` | `for...of` | `noForEach` |
| `require` | ESM `import` | `noCommonJs` |
| `import 'fs'` | `import 'node:fs'` | `useNodejsImportProtocol` |
| An `async` function with no `await` | Remove `async`, and return the promise | `useAwait` |
| `${VAR}` in a normal string | Add a `biome-ignore` with a reason where the text is literal (see `generateCodemieYaml` in `iac/codemie-iac-nodejs/src/lib/backupYamlGenerator.ts`) | `noTemplateCurlyInString` |

## Biome formatter

Two spaces, line width 120, LF, single quotes, semicolons, ES5 trailing commas (`formatter` and `javascript.formatter` in `biome.json`). The npm scripts cover `./src` only, so `jest.config.ts` and `tsup.config.ts` are not checked.

## Ruff (`iac/codemie-iac-python`)

`pyproject.toml` has no ruff section, so default rules and format apply.

## Type safety

| Package | Rule |
|---|---|
| Node.js | `strict` is on (`iac/codemie-iac-nodejs/tsconfig.json`, `compilerOptions.strict`) |
| Node.js | Narrow unknown shapes with a type guard (`iac/codemie-iac-nodejs/src/lib/typeGuards.ts`, `iac/codemie-iac-nodejs/src/lib/validationUtils.ts`) |
| Python | Type a credential field as `CredentialRef`, not `str` (`IntegrationSpec` in `iac/codemie-iac-python/src/codemie_iac/specs/integration.py`) |
| Python | No type checker runs in CI |

## Licence headers

| Files | Header in the file |
|---|---|
| Node.js source | A proprietary "All Rights Reserved" notice (for example `iac/codemie-iac-nodejs/src/lib/logger.ts`) |
| Python source | Apache 2.0 (for example `iac/codemie-iac-python/src/codemie_iac/__init__.py`) |

The Node.js header conflicts with the Apache 2.0 licence that `iac/codemie-iac-nodejs/package.json` declares. No CI gate checks headers. A new file copies the header of its neighbours, and the conflict stays open until a maintainer decides.

## Documentation standards

- Node.js: JSDoc on exported functions where the behaviour is not obvious (`iac/codemie-iac-nodejs/src/lib/mcpSanitizer.ts`).
- Python: a module docstring, and a comment that says why a rule exists (`iac/codemie-iac-python/src/codemie_iac/envelope.py`, `iac/codemie-iac-python/src/codemie_iac/serializer.py`).
- A user-visible CLI option or YAML field needs an entry in the package README.

## Common violations

| Violation | Fix |
|---|---|
| Format failure after an edit | Run the auto-fix commands in `.ai-run/guides/quality-gates.md` |
| A Python model that accepts unknown fields | Add `model_config = ConfigDict(extra="forbid")` |
| A `to_yaml` change that adds `exclude_none=True` | Remove it. It breaks the round trip (`iac/codemie-iac-python/src/codemie_iac/serializer.py`) |
| An internal reference in a test | Use a placeholder such as `https://codemie.example.com` |
