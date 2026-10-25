# deselected_default_tools in codemie-cdk IaC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox syntax.

**Goal:** Back up, deploy, checksum, model and document the assistant list `deselected_default_tools` in the Node and Python IaC packages without changing any output for assistants that don't use it.

**Architecture:** One rule in both packages: empty or absent list means "not set" and leaves every output byte-identical to today. Node deploy is already pass-through (`...sdkFields`, converters.ts:369/486); only backup and checksum change. Python gains a spec field omitted from YAML when empty.

**Tech Stack:** TypeScript/jest/biome (`iac/codemie-iac-nodejs`), Python/pydantic/pytest/poetry (`iac/codemie-iac-python`).

**Spec:** docs/superpowers/tasks/2026-10-25-datasource-default-tools-selection-cdk/spec.md

Commit per task using the repository's existing convention.

## Global Constraints

- Field: `deselected_default_tools`, list of strings; names `get_repository_file_tree`, `search_code_repo`, `search_kb`.
- No client-side validation of names; no defaulting to `[]` on deploy; explicit `[]` must be sent.
- Do not add prompt_variables/categories/slug/tool_permissions to the checksum; no Python backup/import commands; no Node assistant JSON schema.

## Review Focus

- Legacy assistant (no field) checksum equals pre-change hash (pinned in Task 2).
- Reordered/duplicated lists hash equal (Task 2).
- Explicit `[]` reaches `assistants.update` (Task 3).
- Python legacy spec dump unchanged, no `deselected_default_tools` key (Task 4).
- Python request with `None` maps to empty (Task 4).

---

### Task 1: SDK version floors

**Files:** Modify `iac/codemie-iac-python/pyproject.toml:11` (+ `poetry.lock`), `iac/codemie-iac-nodejs/package.json:54`.

Test-first: no — dependency metadata only; Task 4's `from_entity` test fails on an SDK lacking the field.

- [ ] Repo cannot tell which release introduced the field (no node_modules/venv, lock pins python 0.1.686). Find the first published `codemie-sdk-python` and `codemie-sdk` (npm) release whose `AssistantRequestBase`/`AssistantCreateParams` has `deselected_default_tools` (`pip download`/`npm view` + inspect). Set that as the python pin and the node range floor (`>=<ver> <1.0.0`); refresh `poetry.lock`. If no published release carries it, stop and report rather than guessing.

### Task 2: Node backup + checksum

**Files:** Modify `iac/codemie-iac-nodejs/src/lib/converters.ts` (`assistantResponseToResource`, ~l.170), `src/lib/checksumUtils.ts:170-189` (`normalizeAssistantConfig`). Tests: `converters.test.ts`, `checksumUtils.test.ts`, `backupTransformers.test.ts`.

Test-first: yes — backup of an assistant with `['search_kb']` yields the key; currently stripped.

- [ ] Tests: converter includes the list when non-empty, omits key when `[]`/undefined (also through `prepareAssistantForYaml`); checksum: a legacy fixture's hash equals a literal hash computed on the unmodified code (capture before editing), different lists differ, `['search_kb','search_code_repo']` equals reversed and duplicated forms, `[]` equals absent.
- [ ] Implement: converter copies only when `length > 0`; normalizer adds the sorted, de-duplicated list only when non-empty (conditional spread after `conversation_starters`, before `buildConfig`; `JSON.stringify` drops undefined so legacy output is identical).
- [ ] Run `npx jest src/lib` in the package; all pass.

### Task 3: Node deploy/preview pass-through

**Files:** Tests only unless a test fails: `src/lib/converters.test.ts` (`assistantResourceToCreateParams`), `src/deploy.test.ts`, `src/lib/previewUtils` tests/`stateManager.test.ts`. Production fixes (if any) in the file that filters the key.

Test-first: yes — YAML `deselected_default_tools: []` expected in `assistants.update` params; fails if anything filters empty arrays.

- [ ] Tests: list reaches create and update params; key absent in resource gives params without the key; `[]` is sent as `[]`; preview reports changed when only the list differs (uses the Task 2 checksum; stateManager stores the same value).
- [ ] Fix only what the tests expose (cite `deploy.ts:293/345/393`, `assistantHelpers.ts:28`). Run `npx jest`; pass.

### Task 4: Python AssistantSpec

**Files:** Modify `iac/codemie-iac-python/src/codemie_iac/specs/assistant.py` (`AssistantSpec` ~l.370, `from_entity` ~l.408). Tests: `tests/test_specs_assistant.py`, `tests/test_review_fixes.py` style (CR-009), `tests/test_schema.py`.

Test-first: yes — `AssistantSpec(deselected_default_tools=[...])` currently raises (extra forbid).

- [ ] Tests: field accepted; `from_entity` copies it, and treats `None` as `[]`; `from_yaml(to_yaml(b)) == b` with a non-empty list; `to_yaml` of a spec with `[]` has no such key and equals the pre-change dump for a legacy spec; `document_json_schema()` lists the property as not required.
- [ ] Implement `deselected_default_tools: list[str] = Field(default_factory=list)`; `from_entity` uses `request.deselected_default_tools or []`. Omit when empty with a `@model_serializer(mode="wrap")` on `AssistantSpec` that removes the key when the list is empty (`serializer.py` uses `model_dump(mode="json")` without exclude_none, so it must not be changed; validation-mode schema is unaffected). Update the module docstring note. Run `poetry run pytest`; pass.

### Task 5: Docs and examples

**Files:** Modify `iac/codemie-iac-nodejs/examples/assistant-examples.yaml` (header field list l.5-70 + one example with all three names), optionally one `examples/modular-config-example/configs/assistants/*.yaml`, `iac/codemie-iac-nodejs/README.md`, `iac/codemie-iac-python/README.md` (Assistant section l.253-280).

Test-first: no — documentation; if a test loads the example YAML it must still pass.

- [ ] Document name, allowed values, absent/empty = all default tools on, omitted key keeps platform value on deploy, explicit `[]` re-enables all; Python README notes omission when empty. Run Node jest and pytest for example-loading tests.
