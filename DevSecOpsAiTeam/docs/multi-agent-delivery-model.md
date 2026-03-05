# Multi-Agent Epic Delivery Model

## Scope and Principles

- Jira Epic is the system of record.
- All decisions, approvals, and evidence must be linked to the Epic.
- One customer contact exists: Epic creator.
- Customer communication happens only in the Epic (description/comments/custom fields).
- All delivery roles are AI agents; Epic creator/customer is the only human participant.

## Agent Roles

- Scrum Master Agent (Orchestrator)
  - Monitors new Epics.
  - Coordinates all agents.
  - Resolves blockers.
  - Owns all Epic status transitions.
- Product Owner / Requirements Agent
  - Customer-facing communication in Epic.
  - Clarifies requirements, AC, NFRs.
  - Maintains open questions, assumptions, decisions.
  - Ensures Definition of Ready.
- Architect Agent
  - Solution design and ADRs.
  - Task/subtask breakdown.
  - Security review request.
- Security Architect Agent
  - Threat model light, controls, sign-off.
- DevOps/IaC Agent
  - Repo bootstrap, CI/CD, environments, IaC, policy-as-code.
- Developer Agents
  - Implementation, tests, PRs.
- Tester/QA Agent
  - Test plan, e2e/regression evidence, quality gate.
- FinOps Agent
  - Cost model, tagging, budget guardrails.
- Release Manager Agent
  - Release readiness, notes, rollout/rollback.

## Mandatory Epic Data

- Customer communication log:
  - Open Questions
  - Customer Answers
  - Assumptions
  - Decisions
- Risk classification:
  - Risk Level: `Low|Medium|High`
  - Drivers: data sensitivity, internet exposure, auth changes, prod impact, cost delta
- Approval tracking:
  - Budget exception status
  - Policy gate change status
  - Links to approval artifacts

## Epic Workflow

- `NEW (Intake)`
- `TRIAGE`
- `READY FOR REFINEMENT`
- `IN REFINEMENT`
- `READY FOR DELIVERY`
- `IN DELIVERY`
- `READY FOR RELEASE`
- `RELEASING`
- `DONE`
- `BLOCKED` (from any status)

Rule: only Orchestrator transitions Epic status.

## Approvals

- Required for:
  - Budget exception
  - Policy gate change
- Approval artifacts:
  - Jira approval issue linked to Epic, or
  - Confluence approval section/page linked to Epic
- No exception execution without linked approval artifact.

## Rework Stop Condition

- After 3 failed review iterations, ask customer in Epic to decide:
  - De-scope
  - Approve extra scope/time
  - Accept risk exception

## Evidence Linking Rules

- PRs must include Jira key.
- Pipelines/scans must be linkable.
- Confluence artifacts (design, ADR, security, runbook, release notes) must link to Epic.
- Epic must include an evidence graph of all artifacts.
