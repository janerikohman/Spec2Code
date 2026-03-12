# Phase 2 Implementation Checklist (No Architecture/Logic Change)

## Non-Negotiable Constraint

Phase 2 is execution-hardening only.

- Do **not** change Phase 1 architecture.
- Do **not** refactor orchestration topology.
- Do **not** move responsibilities between `epic-scheduler` and `review-endpoint`.
- Fix blockers with targeted patches in existing flow.

## Phase 2 Outcome Contract (Per Epic)

An epic is only complete when output includes all of the following:

1. Running application URL in Azure
2. Test results artifact (summary + detailed evidence)
3. Deployment evidence (pipeline run + infra/app deployment status)
4. Closed stories with implementation notes and links
5. Final Jira epic comment with end-to-end summary

## Implementation Status (Current Branch)

- ✅ Item 1 implemented: coordinator auto-finalizes dispatch stories after gate pass.
- ✅ Item 2 implemented: structured completion comments are posted on stories.
- ✅ Item 3 implemented: security findings must be explicitly dispositioned by architecture before gate pass can remain true.
- ✅ Item 4 implemented: delivery is blocked when developer application-code evidence is missing (infra-only evidence cannot pass).
- ✅ Item 5 implemented: delivery is blocked without CI/CD run evidence and explicit pipeline pass indication.
- ✅ Item 6 implemented: delivery is blocked without Azure runtime URL and health-check evidence.
- ✅ Item 7 implemented: final epic output contract is enforced (app URL + test evidence + deployment proof + traceability).
- ✅ Item 8 implemented: transition discipline enforced with retry path checks; epic is blocked if dispatch closure discipline is not satisfied.
- ✅ Item 9 implemented: per-role DoD artifact/evidence enforcement blocks completion when mandatory role outputs are incomplete.
- ✅ Item 10 implemented: traceability matrix gate enforces Jira↔code↔pipeline↔runtime linkage coverage.
- ✅ Item 11 implemented: retry/escalation visibility added via structured Jira comments and transition-attempt traces.

## Checklist (Mapped to Current Gaps)

### 1) Stories must not stay open after work is complete

**Requirement**
- Every story created by orchestration must transition to `Done` when its role output is accepted.

**Acceptance Criteria**
- No story remains open if the linked deliverable is already produced.
- Story status reflects actual execution state.

**Evidence Required**
- Jira transition log or status history link in final epic summary.

---

### 2) Story updates must contain what was done

**Requirement**
- Each agent updates its story with structured completion notes before closure.

**Acceptance Criteria**
- Story contains: scope completed, artifacts produced, blockers (if any), and links.
- Closure comment is present on every completed story.

**Evidence Required**
- Jira comment links per story.

---

### 3) Security findings must be acknowledged by architecture

**Requirement**
- Security review outputs must be consumed by architecture with explicit decision records.

**Acceptance Criteria**
- For each security finding: `Accepted`, `Mitigated`, or `Deferred` decision exists.
- Architect output references security finding IDs.

**Evidence Required**
- Linked architecture note/ADR + security finding mapping table.

---

### 4) Delivery must include application code, not infra only

**Requirement**
- Developer output must include application implementation artifacts in repo/PR scope.

**Acceptance Criteria**
- PR/repo contains both infra and app code changes for the epic scope.
- Missing app code blocks epic completion.

**Evidence Required**
- Commit/PR links showing app code paths and infra paths.

---

### 5) End-to-end setup must run (code + pipeline)

**Requirement**
- Pipeline must execute build/test/deploy path for the delivered epic.

**Acceptance Criteria**
- CI pipeline passes required stages.
- Failed gates prevent `Done` status at epic level.

**Evidence Required**
- Pipeline run URL + stage results summary.

---

### 6) Infra must be created and app must run in Azure

**Requirement**
- Delivery is valid only if target Azure infra exists and app is reachable.

**Acceptance Criteria**
- Infra provisioning success is recorded.
- App health endpoint or equivalent runtime check passes.

**Evidence Required**
- Deployment logs + runtime URL + health check output.

---

### 7) Epic output must provide user-visible app + test evidence

**Requirement**
- Final epic output must be consumable by user without digging through internals.

**Acceptance Criteria**
- Epic comment contains app URL, test report link, and final status table.
- Tester agent report is attached or linked.

**Evidence Required**
- Final Jira epic comment permalink with all links.

---

### 8) Enforce state transition discipline

**Requirement**
- Story lifecycle transitions follow agreed state machine with no skipped terminal updates.

**Acceptance Criteria**
- All stories move through valid states only.
- Invalid transitions are flagged and retried/escalated.

**Evidence Required**
- State transition trace in orchestration output.

---

### 9) Enforce Definition of Done by role

**Requirement**
- Each role must satisfy mandatory artifacts before handoff.

**Acceptance Criteria**
- Missing mandatory artifact blocks downstream completion.
- Role handoff includes evidence payload.

**Evidence Required**
- Per-role DoD checklist attached in epic summary.

---

### 10) Improve traceability across Jira, repo, pipeline, deployment

**Requirement**
- Every story and final epic comment must cross-link issue ↔ code ↔ pipeline ↔ runtime.

**Acceptance Criteria**
- No orphaned updates (text with no linkable evidence).
- Links are valid and accessible.

**Evidence Required**
- Traceability matrix in final epic summary.

---

### 11) Add explicit retry/escalation visibility

**Requirement**
- Agent failures are visible, retried with limits, then escalated with reason.

**Acceptance Criteria**
- Retry attempts and final outcome are posted.
- Escalation path is visible in epic updates.

**Evidence Required**
- Failure/retry log summary in Jira comments.

## Execution Order (Recommended)

1. Story closure + structured story comments
2. Security-to-architecture decision linkage
3. App code presence enforcement
4. CI gate enforcement for epic completion
5. Deployment/runtime evidence contract
6. Final epic summary standardization
7. Retry/escalation transparency

## Phase 2 Definition of Done

Phase 2 is complete when at least one new epic runs through the unchanged Phase 1 architecture and exits with:

- all related stories closed with structured evidence,
- security findings reconciled by architecture,
- app + infra delivered,
- pipeline green,
- Azure app URL reachable,
- tester report linked,
- final epic comment containing full traceability.
