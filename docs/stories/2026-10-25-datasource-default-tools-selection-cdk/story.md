# CDK: Preserve Deselected Default Tools in Assistant Import/Export — Story

**Date**: 2026-10-25
**Status**: Approved
**Ticket**: —
**Parent**: datasource-default-tools-selection (workspace story `docs/stories/2026-10-16-datasource-default-tools-selection/story.md`, outside this repository)
**Feature**: datasource-default-tools-selection
**Depends on**: Backend story and SDKs story of the same parent (other repositories; already implemented)

---

## Context

- The infrastructure-as-code tooling lives in the `codemie-cdk` repository, in a Node package and a Python package. The SDKs story assumed it lived in the SDK repository, so its backup, import and checksum criteria are not covered there.
- The Node package backs up existing assistants to YAML, deploys and imports assistants from YAML, previews changes, and decides whether an assistant changed by comparing checksums. Backup copies a fixed list of assistant settings, and the checksum uses a fixed list too; neither includes the deselected default tools setting.
- The Python package is a specification library only (no backup or import command). Its assistant specification rejects unknown settings and does not carry the new one when built from an existing assistant.
- Result today: backing up an assistant with a deselected default tool and restoring it can silently turn the tool back on, and changing only that setting is not detected as a change.
- Existing settings that the checksum already ignores (prompt variables, categories, slug, tool permissions) are a known gap of the same kind and are not part of this story.
- Delivery order: this story follows the backend and SDKs stories.

---

## Complexity

**Size**: M (18/36) · **Recommended flow**: sdlc-standard

Two packages in one repository, about 8-10 files, each edit small; the care is in keeping checksums stable for existing assistants and keeping Node and Python consistent.

---

## Story

**As a** platform engineer managing assistants as code with the CodeMie IaC tooling, **I want** the deselected default datasource tools of an assistant to be backed up, deployed, imported and compared like any other assistant setting **so that** a deselected tool such as the repository tree stays off after a backup/restore or redeploy and changes to it are visible in previews.

---

## Background

Teams that manage assistants as code need the same control as authors using the UI. Without this change, a backup followed by a restore into another environment, or an import from YAML, can turn an expensive tool back on without anyone noticing, and a preview reports "no changes" when only that setting differs.

---

## Acceptance Criteria

- [ ] Given an assistant with deselected default tools, when it is backed up with the Node tooling, then the generated YAML contains the deselected tools.
- [ ] Given an assistant with no deselected default tools, when it is backed up, then the generated YAML does not mention the setting and is identical to today's output.
- [ ] Given a YAML config listing deselected default tools for an assistant, when it is deployed or imported with the Node tooling, then the setting is saved on the platform and returned in subsequent reads.
- [ ] Given an assistant is backed up and then deployed into another environment, when it is read back, then the same default tools are deselected.
- [ ] Given a YAML config for an existing assistant that does not mention deselected default tools, when it is deployed, then an existing deselection on the platform is left unchanged.
- [ ] Given a YAML config that lists an empty set of deselected default tools, when it is deployed, then all default tools of that assistant are selected again.
- [ ] Given two assistants that differ only in their deselected default tools, when the tooling compares them, then they are treated as different, and a preview reports the assistant as changed.
- [ ] Given existing assistants with no deselected default tools, when a preview or deploy runs after this change, then none of them is reported as changed because of this setting.
- [ ] Given two assistants whose deselected default tools are the same tools listed in a different order, when the tooling compares them, then they are treated as identical.
- [ ] Given the platform rejects a YAML config (for example an unknown tool name in the deselected list), when the deploy runs, then the error is reported to the user and not silently swallowed.
- [ ] Given the Python tooling, when an assistant specification includes deselected default tools, then it is accepted, kept when built from an existing assistant, and written out in the generated YAML only when at least one tool is deselected.
- [ ] Given the Python tooling and an assistant with no deselected default tools, when its specification is generated, then the output is identical to today's.
- [ ] Given the examples and documentation of both packages, when a user looks up assistant settings, then the setting is described with an example and the three tool names it accepts.

---

## Out of Scope

- Backend behaviour, the UI and the SDK packages.
- Adding a backup or import command to the Python package.
- Client-side validation of tool names or variant conflicts; the platform decides.
- Other settings the checksum already ignores (prompt variables, categories, slug, tool permissions).
- Changes to provider, Git or MCP tool handling.

---

## Decisions

- D1: Which IaC packages are covered? → Both Node and Python, to avoid drift between them. — user
- D2: Effect on checksums for existing assistants → An empty or absent setting counts the same as today, so existing assistants are not reported as changed. — user
- D3: What does an omitted setting in a YAML config mean on deploy? → The deselection stays as it is on the platform, per the parent criterion that deselected tools stay deselected across versions, restore, export/import and workflow use. Re-enabling needs an explicit empty list. — user
- D4: Should the tooling validate tool names client-side? → No. It relies on the platform response and surfaces its errors, consistent with the SDKs story. — proposed by PO: avoids duplicating server rules
- D5: Does the order of the listed tools count as a change? → No. The same tools in a different order are identical. — proposed by PO: prevents false "changed" reports from a harmless reordering
- D6: Which SDK versions must the IaC packages require? → A release that carries the setting; raising the minimum is part of this story. — proposed by PO: the Python package pins an older SDK release and the Node package accepts a wide range, so the setting could be dropped by an older SDK

---

## Open Questions

- None
