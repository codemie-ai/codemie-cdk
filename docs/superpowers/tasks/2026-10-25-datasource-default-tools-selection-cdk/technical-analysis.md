# Technical Research

**Task**: assistant backup import export converters checksum deselected default tools datasource codemie-iac-nodejs codemie-iac-python
**Generated**: 2026-10-25
**Research path**: filesystem

---

## 1. Original Context

Add a child story for repository codemie-cdk (iac/codemie-iac-nodejs and iac/codemie-iac-python) covering assistant import/export (backup/import, converters, transformers, checksums, YAML config schema/validation, examples, docs) support for the new assistant-level list of deselected default datasource tools. Parent story: docs/stories/2026-10-16-datasource-default-tools-selection/story.md (backend, UI and SDK parts are already implemented; the SDK child story at docs/stories/2026-10-16-datasource-default-tools-selection/children/datasource-default-tools-selection-sdks/story.md assumed IaC lived in codemie-sdk, but IaC actually lives in codemie-cdk/iac). Without this change, backup/import/deploy through the IaC tooling would drop the field, a round trip could silently re-enable a deselected tool, and checksums would not detect the change. Determine: the exact field name/shape as implemented in codemie (backend) and codemie-sdk (Python/Node models); where in codemie-cdk the assistant is exported (backup), imported/deployed, normalized, transformed, checksummed, validated (schema), documented and exemplified in both the Node and Python IaC packages; existing tests that cover these; risks (checksum stability for existing assistants, field stripping, drift between Node and Python).

---

## 2. Codebase Findings

### Field contract (reference repos, read-only)
- Name: `deselected_default_tools`, a list of strings. Absent/empty means all default tools on.
- Backend `codemie/src/codemie/rest_api/models/assistant.py`: `VALID_DESELECTABLE_DEFAULT_TOOLS = {"get_repository_file_tree", "search_code_repo", "search_kb"}` (line 69); response/base model `list[str]` default `[]` (l.332); DB columns JSONB on assistant (l.660) and version (l.1294); `_validate_deselected_default_tools` (l.1008) rejects unknown names with "Unknown deselected default tools detected: ...". Versions copy it (`assistant_version_service.py`). Alembic `64825fe31931_add_deselected_default_tools.py`.
- Python SDK `codemie-sdk/sdk/codemie-python/src/codemie_sdk/models/assistant.py`: `Assistant.deselected_default_tools: list[str]` default `[]` (l.275); `AssistantRequestBase.deselected_default_tools: list[str] | None = None` (l.312, inherited by `AssistantCreateRequest`/`AssistantUpdateRequest`); `AssistantVersion` `list[str]` default `[]` (l.432). `AssistantBase` (l.158) does NOT have it.
- Node SDK `codemie-sdk/sdk/codemie-nodejs/src`: `models/assistant.ts` l.103 `deselected_default_tools: string[]` on `Assistant` (response, required) and `AssistantVersion` (l.177); the create/update param interface carries `deselected_default_tools: string[]` too; zod `schemas/assistant.ts` l.114 `z.array(z.string()).optional()`; `services/assistant.ts` l.88/96/201 normalise missing to `[]` on reads. Param interface has `[key: string]: unknown`.
- SDK source version in repo is 0.1.0 (both); the Python IaC pins released `codemie-sdk-python = "0.1.686"`; Node IaC peer/dep `codemie-sdk ">=0.1.0 <1.0.0"`. Which released versions contain the field was not determinable from the filesystem.

### codemie-cdk: Node package `iac/codemie-iac-nodejs` (full backup/import/deploy CLI)
- `src/types/codemieConfig.ts` l.135 `AssistantResource extends Partial<Omit<AssistantCreateParams, ...>>`: SDK fields inherited, so the field type comes from the installed SDK; no explicit field declared.
- Backup/export: `src/backup.ts` -> `src/lib/backupTransformers.ts` `prepareAssistantForYaml` (l.158) which spreads `assistantResponseToResource(assistant)` from `src/lib/converters.ts` l.170. That function is a hand-written whitelist (name, description, prompt, model, temperature, top_p, shared, is_react, is_global, icon_url, conversation_starters, toolkits, context, mcp_servers, sub_assistants, prompt_variables, categories). `deselected_default_tools` is NOT copied: it is stripped on backup. Also writes state `configChecksum: calculateAssistantConfigChecksum(finalAssistant)` (l.190). `src/lib/backupYamlGenerator.ts` serialises the resource to YAML.
- Import/deploy: `src/import.ts`, `src/deploy.ts` (checksum compare l.214/282, `client.assistants.update` l.293/345/393), `src/lib/assistantHelpers.ts` l.28 (`client.assistants.create`), `src/lib/previewUtils.ts` l.310 (preview change detection), `src/lib/stateManager.ts` l.127. Conversion to SDK params: `converters.ts` `assistantResourceToCreateParams` (l.472) destructures IaC-only fields and spreads `...sdkFields`, so a `deselected_default_tools` key present in YAML passes through unchanged on create and update. No defaulting, no explicit mapping (unlike `prompt_variables: assistant.prompt_variables || []`). A YAML that omits the key sends nothing; the effect of omission on update (keep vs reset) depends on backend update semantics, not traced here (SDK request type is `None` default).
- Checksum: `src/lib/checksumUtils.ts` `normalizeAssistantConfig` (l.170) is a whitelist, fixed order, `JSON.stringify`: description, model, temperature, top_p, shared, is_react, is_global, icon_url, toolkits, context, mcp_servers, assistant_ids, sub_assistants, skills, conversation_starters, buildConfig. Not included: `deselected_default_tools` (also `prompt_variables`, `categories`, `slug`, `tool_permissions` - existing omissions). A change to the list therefore does not change the checksum, and deploy/preview treat the assistant as unchanged.
- Validation: `src/lib/codemieConfigLoader.ts` `validate` (l.132-154) checks only prompt/config file presence, description, model. `src/lib/validationUtils.ts` handles slugs. No YAML JSON-schema for assistants exists in the Node package (`src/appConfig/configSchema.ts` is app config, not resource schema). Types are the only schema.
- Examples/docs: `examples/assistant-examples.yaml` (header field list l.5-70, field-by-field examples), `examples/modular-config-example/configs/assistants/*.yaml`, `README.md`. No mention of the field (grep for "deselected" across all of `iac/` returns nothing).

### codemie-cdk: Python package `iac/codemie-iac-python` (library only: spec models + YAML serializer, no backup/import CLI)
- `src/codemie_iac/specs/assistant.py` `AssistantSpec` (`ConfigDict(extra="forbid")`) with explicit `from_entity(request: AssistantCreateRequest)`. It lists fields one by one and lacks `deselected_default_tools`. `from_entity` silently drops it; a YAML containing it fails validation (extra forbidden). Docstring explicitly calls out the earlier `tools_tokens_size_limit` omission as a data-loss bug class (CR-009, CR-007/CR-011).
- `src/codemie_iac/envelope.py` maps `DocumentKind.ASSISTANT` to `AssistantSpec`; `schema.py` `document_json_schema()` derives JSON Schema from the Pydantic model (so the schema updates automatically when the spec gains the field); `serializer.py` `to_yaml` uses `model_dump(mode="json")` without `exclude_none`, so an added field is always emitted (existing YAML dumps would gain `deselected_default_tools: []`).
- Docs: `README.md` Assistant section (l.253-280) states AssistantSpec "has more fields than this". No example mentions the field.

---

## 3. Documentation Findings

### Guides and Architecture Docs
No `.ai-run/guides/` in codemie-cdk checked; `codemie-cdk/docs` holds only `RELEASING.md`. Conventions derived from code. The parent story and the SDK child story describe the contract; the SDK child story wrongly assumed IaC lived in codemie-sdk.

### Architectural Decisions
Parent story: only the deselected list is stored (D3); nothing deselected means all on (D2); no server validation of conflicting variants (D1). Export/import must keep the tool deselected (AC "exported/imported ... stays deselected").

### Derived Conventions
- Node: resource fields whitelisted in two places (backup converter, checksum normaliser); deploy is pass-through via spread.
- Python: every field enumerated in the Spec and in `from_entity`; `extra="forbid"`.
- Nested defaults use `|| []` (Node) / `Field(default_factory=list)` (Python).

---

## 4. Testing Landscape

### Existing Coverage
- Node (jest, colocated `*.test.ts`): `src/lib/converters.test.ts` (prompt_variables included when present/empty l.503-532; `assistantResponseToResource` and create-params cases), `src/lib/checksumUtils.test.ts` (assistant normalise/checksum), `src/lib/backupTransformers.test.ts` (prepareAssistantForYaml; asserts `tools_tokens_size_limit` is absent l.244), `src/backup.test.ts`, `src/import.test.ts`, `src/deploy.test.ts`, `src/lib/assistantHelpers.test.ts`, `src/lib/backupYamlGenerator.test.ts`, `src/lib/stateManager.test.ts`, `src/testFixtures.ts`. No existing test references deselected tools.
- Python (pytest, `tests/`): `test_specs_assistant.py` (roundtrip incl. MCP, extra-forbid rejection l.170), `test_review_fixes.py` (CR-009 `tools_tokens_size_limit` preserved: template for a new test), `test_serializer.py`, `test_schema.py`, `test_envelope.py`, `test_branch_review_fixes.py`.

### Testing Framework and Patterns
Jest with ts-jest style config (`jest.config.ts`), biome lint; pytest with pydantic models. Round-trip tests `from_yaml(to_yaml(b)) == b` exist in Python.

### Coverage Gaps
No test for the field in either package; no test that checksum stays stable for assistants without the field (existing checksum tests use fixed inputs but none pin a hash of a legacy shape was verified).

---

## 5. Configuration and Environment

### Environment Variables
Not relevant to this feature (`.env.template` in Node covers credentials/URLs).

### Configuration Files
`codemie.yaml` plus `examples/modular-config-example/configs/assistants/*.yaml` (assistant YAML); state file stores `configChecksum` per assistant (`stateManager.ts`).

### Feature Flags and Deployment Concerns
No flags. Dependency version gates: the Python pin `codemie-sdk-python==0.1.686` and Node `codemie-sdk` range must resolve to an SDK release that contains the field (unconfirmed).

---

## 6. Risk Indicators

- Speculative: checksum stability. Adding `deselected_default_tools` to `normalizeAssistantConfig` changes the JSON string and so the hash for every existing assistant unless the key is omitted when empty/undefined; otherwise the first deploy/preview after upgrade marks all assistants changed (stored `configChecksum` in state and backup-generated state). Include-only-when-non-empty (or normalise sorted, absent == []) keeps legacy hashes stable.
- Field stripping on backup: `assistantResponseToResource` whitelist drops the field; restoring such a backup via `update` could re-enable a deselected tool (depends on backend update semantics when the key is omitted; not traced).
- Speculative: list order. If order is not normalised, YAML reordering would alter checksum; sort and dedupe decisions needed.
- Node/Python drift: Node passes unknown SDK fields through (`...sdkFields`) and has no schema; Python is `extra="forbid"` with an explicit `from_entity`. Same field must be added in both with the same name, shape, and empty-list default; Python `to_yaml` emits non-None defaults, so choosing `list` default `[]` vs `None` changes emitted YAML for all assistants.
- Python SDK type asymmetry: request model uses `list[str] | None`, response uses `list[str]`; `from_entity` takes a request.
- No client-side validation of tool names (backend rejects unknown names; allowed: `get_repository_file_tree`, `search_code_repo`, `search_kb`).
- SDK version availability for the pinned/range dependencies is unverified; Node type of `AssistantResource` depends on the installed SDK.
- Existing checksum whitelist already omits `prompt_variables`, `categories`, `slug`, `tool_permissions`; out of scope but same bug class.
- Python package has no backup/import code, so "backup/import" for Python means spec model, schema, serializer and README only.

---

## 7. Summary for Complexity Assessment

Two packages, small change surface each. Node: `converters.ts` (backup whitelist, optional explicit create mapping), `checksumUtils.ts` (normalisation), types (inherited), plus tests, example YAML and README. Python: `specs/assistant.py` (field and `from_entity`), tests, README; JSON schema follows automatically. Roughly 6-10 source and test files plus docs/examples. Deploy path is already pass-through, so most work is backup export, checksum and the Python spec.

Technical novelty is low: it mirrors how `prompt_variables` and `tools_tokens_size_limit` were handled. Main design points are the checksum rule that preserves hashes of existing assistants and agreeing on default and omission semantics across both packages. Test posture is good: both packages have colocated tests for each touched function, but none for this field.

Key risks: checksum churn for existing assistants, silent field loss on backup/restore, Node/Python divergence, and SDK dependency version availability.

---

## 8. External References

None named by the task as an outside source beyond the repositories listed. Parent and SDK child story paths were referenced for context; their contract content was verified directly against code in `codemie` and `codemie-sdk` (see Section 2).
