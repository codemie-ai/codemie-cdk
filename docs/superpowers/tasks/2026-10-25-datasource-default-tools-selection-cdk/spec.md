# Spec: deselected_default_tools in codemie-cdk IaC (Node and Python)

Story (settled, D1-D6): docs/stories/2026-10-25-datasource-default-tools-selection-cdk/story.md
Size: M (18/36). Research: technical-analysis.md in this directory.

## Problem

The assistant setting `deselected_default_tools` (list of strings; allowed `get_repository_file_tree`, `search_code_repo`, `search_kb`; absent or empty means all default tools on) is dropped by Node backup, ignored by the Node checksum, and rejected or dropped by the Python AssistantSpec. A backup/restore can silently re-enable a deselected tool and a preview reports "no changes" when only this differs.

## Design

Single rule in both packages: an empty or absent list is "not set" and leaves every output byte-identical to today.

### Node (`iac/codemie-iac-nodejs`)
- Backup: `assistantResponseToResource` (src/lib/converters.ts) copies the list only when non-empty. Absent from YAML otherwise, so backups of unaffected assistants are unchanged.
- Deploy/import: the create/update path already passes unknown keys through (`...sdkFields` in `assistantResourceToCreateParams`). Required behavior: a key absent from YAML sends nothing (platform keeps its deselection, D3); an explicit `[]` is sent as `[]` (re-enables all tools) and must not be filtered out anywhere along the path. No defaulting to `[]`.
- Checksum: `normalizeAssistantConfig` (src/lib/checksumUtils.ts) includes the list only when non-empty, sorted (and de-duplicated) so order does not matter (D5). Legacy assistants hash exactly as before (D2). Consequence, accepted: YAML `[]` vs absent hash the same, so switching an assistant from deselected to explicit `[]` is detected via the non-empty-to-empty change, but a never-set assistant gaining `[]` is not a change.
- Preview/state: preview and stateManager use the same checksum, so no separate change is expected; verify by test.
- Errors: platform rejection (unknown tool name) propagates through existing error handling; no client-side validation (D4).
- Types: `AssistantResource` inherits the field from the SDK type; raise the `codemie-sdk` minimum to a release that carries it (D6).

### Python (`iac/codemie-iac-python`)
- `AssistantSpec` (src/codemie_iac/specs/assistant.py) gains `deselected_default_tools: list[str]`, default empty list, same name and shape as Node.
- `from_entity` copies it from the request (treating None as empty), per the CR-009 precedent.
- Serialization: emitted in YAML only when non-empty; JSON Schema derives from the model automatically and should list the field as optional. Existing dumps stay identical (D1/AC).
- Raise the `codemie-sdk-python` pin to a release that carries the field (D6).

### Docs and examples
- Node: `examples/assistant-examples.yaml` (header field list plus one example showing all three tool names), one modular example if natural, README.
- Python: README Assistant section with an example and the three names.

## Acceptance criteria

Those of the story (13 items) apply verbatim. Verification maps to tests:
- Node converters: field present when non-empty, absent when empty/undefined.
- Node checksum: legacy fixture hash unchanged; differing lists differ; reordered lists equal; empty equals absent.
- Node deploy/preview: YAML with list reaches `assistants.update/create` params; absent key does not add the key; `[]` is sent; preview flags a list-only change.
- Python: accepted, round-trips via `from_entity`, YAML omits when empty, identical output for legacy specs, schema contains the field.

## Non-goals

- Backend, UI, SDK packages.
- Adding backup/import commands to the Python package.
- Client-side validation of tool names or variant conflicts.
- Adding prompt_variables, categories, slug or tool_permissions to the checksum.
- Changes to provider, Git or MCP tool handling.
- A YAML JSON schema for Node assistants.
