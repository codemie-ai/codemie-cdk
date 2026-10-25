---
schema: sdlc-factory/code-review@1
decision: approve
reviewed_head: 2b3a09b056ceebe03004c77b4d0ad6e4ef0bbfbd
---

# Code review — 2026-10-25-datasource-default-tools-selection-cdk

**Decision:** approve (check round, confidence final low · check high)  
**Reviewed head:** `2b3a09b` · **Rounds:** final → check

**Closed:** 2 fixed · 0 moot · 0 decided

Both prior blocking findings are resolved by reading current source: previewUtils.test.ts now tests that preview flags an update when only deselected_default_tools changes (plus a no-change control), and the Python README has an example snippet with the three tool names. Tests were not executed (Stage 7 owns execution); deferred SDK-floor items were not re-checked.

## Open — 0

## Pre-existing (not blocking) — 2

- **Node codemie-sdk floor not raised** — `iac/codemie-iac-nodejs/src/types/codemieConfig.ts:155` — field declared locally with TODO; no dependency floor change. Out of scope: the original task records the user-approved decision that no published SDK carries the field, so the floor is raised later.
- **Python codemie-sdk-python pin not raised** — `iac/codemie-iac-python/src/codemie_iac/specs/assistant.py:409` — field declared locally with TODO; no pin change. Out of scope: same user-approved SDK decision in the original task.

## Coverage

Graded at the final round; the check round re-verified the findings, not these rows — Open and Closed above are current.

| Acceptance criterion | Status | Notes |
|---|---|---|
| Node backup: assistantResponseToResource copies deselected_default_tools only when non-empty | pass | converters.ts spreads only when length>0; tests cover cases |
| Node deploy/import: absent sends nothing, [] sent as [], non-empty passes through | pass | no code change needed; tests cover list, [] and absent |
| Node checksum: only when non-empty, sorted, de-duplicated; legacy hash unchanged | pass | checksumUtils.ts:187-191 with tests |
| Node preview/state use same checksum; verify by test that preview flags a list-only change | partial (final round) | only checksum-level tests; no preview or stateManager test |
| Node errors: platform rejection propagates, no client-side validation | pass | no validation added |
| Node types: raise codemie-sdk minimum to a release carrying the field (D6) | fail (final round) | local declaration with TODO; deferred per user-approved SDK decision |
| Python AssistantSpec gains deselected_default_tools: list[str], default empty | pass | assistant.py:409-413 with test |
| Python from_entity copies field, None treated as empty | pass | tests cover set, missing, None |
| Python serialization: YAML emits only when non-empty; schema optional | pass | serializer, roundtrip and schema tests |
| Python: raise codemie-sdk-python pin to a release carrying the field (D6) | fail (final round) | local declaration with TODO; deferred per user-approved SDK decision |
| Docs Node: examples header list, example with three names, README | pass | assistant-examples.yaml and README updated |
| Docs Python: README Assistant section with an example and the three names | partial (final round) | README.md:283-293 prose names only, no example snippet |
| Non-goals respected | pass | unrelated python .gitignore addition is out of spec scope |

Standards: commit-format na · code-quality na · security na
