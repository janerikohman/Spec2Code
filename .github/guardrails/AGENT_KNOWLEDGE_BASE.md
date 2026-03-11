# Agent Knowledge Base

Purpose: prevent repeat troubleshooting loops by capturing resolved blockers and preferred resolution paths.

## Entry Template

- Date:
- Area:
- Symptom:
- Root cause:
- Preferred fix path:
- Anti-patterns to avoid:
- Verification:
- Owner:

---

## 2026-03-11 - Foundry runtime API mismatch

- Date: 2026-03-11
- Area: AI Foundry runtime invocation
- Symptom: Runtime failed with missing `create_thread` capability.
- Root cause: Installed SDK/runtime exposed assistant discovery but not thread/run runtime APIs.
- Preferred fix path:
  1. Keep strict agent-core orchestration.
  2. Use Foundry OpenAI responses client path for invocation.
  3. Preserve role system prompts and strict JSON parsing.
  4. Fail fast on invalid outputs (no static fallback).
- Anti-patterns to avoid:
  - Re-introducing static fallback orchestration.
  - Assuming thread/run APIs exist without runtime validation.
- Verification:
  - Guardrails pass: `.github/guardrails/check_agent_guardrails.sh`
  - Legacy scan passes: `.github/guardrails/check_no_legacy_agent_core.sh`
- Owner: coordinator runtime

## 2026-03-11 - Legacy/outdated artifact drift

- Date: 2026-03-11
- Area: repository hygiene
- Symptom: Coexisting `v1` and draft artifacts caused stale references and ambiguity.
- Root cause: historical files were retained after newer canonical artifacts were introduced.
- Preferred fix path:
  1. Create canonical non-legacy files.
  2. Update all references.
  3. Delete superseded `v1`/draft files.
  4. Enforce with guardrail scanner for names and stale references.
- Anti-patterns to avoid:
  - Keeping multiple active versions without explicit migration policy.
  - Leaving references to removed files.
- Verification:
  - No stale refs found by guardrail scripts.
- Owner: repo hygiene

## 2026-03-11 - Azure resource and cost discipline baseline

- Date: 2026-03-11
- Area: Azure operations
- Symptom: Risk of cost drift and unused resource accumulation over time.
- Root cause: no explicit immutable guardrail requiring hygiene + cost-first decisions.
- Preferred fix path:
  1. Enforce immutable coordinator rules for resource hygiene and cost-first choices.
  2. Require best-practice application for Azure operations.
  3. Capture future cleanup/cost incidents in this knowledge base.
- Anti-patterns to avoid:
  - Provisioning without lifecycle ownership and cleanup criteria.
  - Choosing non-minimal SKUs without justified requirement.
- Verification:
  - Coordinator rule tags include RULE_11..RULE_14.
  - Guardrail checks pass.
- Owner: platform governance

## 2026-03-11 - Compliance drift in active docs and test scripts

- Date: 2026-03-11
- Area: repo-wide guideline adherence
- Symptom: Active docs referenced GitHub flows; test scripts used hardcoded function-key fallback paths.
- Root cause: historical migration leftovers and convenience shortcuts in test tooling.
- Preferred fix path:
  1. Align active epic/orchestration docs to Bitbucket pipeline wording.
  2. Remove hardcoded function keys and retrieve keys from Azure CLI at runtime.
  3. Treat fallback indicators in test output as non-compliant signals.
  4. Re-run guardrail checks and targeted grep scans.
- Anti-patterns to avoid:
  - Embedding function keys or tokens in source scripts.
  - Keeping active docs inconsistent with mandated delivery toolchain.
- Verification:
  - `.github/guardrails/check_agent_guardrails.sh`
  - `.github/guardrails/check_no_legacy_agent_core.sh`
  - grep scans for hardcoded key and outdated filenames return no active violations.
- Owner: compliance sweep
