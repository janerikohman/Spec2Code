import base64
import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib import parse, request

import azure.functions as func

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

REQUIRED_ITEMS = [
    ("business_goal", "Business goal/problem statement", "What business problem are we solving, and what outcome is expected?"),
    ("personas", "Target users/personas", "Which users/personas are impacted, and how?"),
    ("scope", "Scope boundaries", "What is in scope and explicitly out of scope for this Epic?"),
    ("acceptance_criteria", "Acceptance criteria", "Please provide testable acceptance criteria for key user flows."),
    ("dependencies", "Dependencies and constraints", "What dependencies, integrations, or blockers should engineering know?"),
    ("nfrs", "Non-functional requirements", "What security/performance/compliance requirements apply?"),
    ("success_metrics", "Success metrics", "How will success be measured after release (KPI/metric)?"),
    ("rollout_plan", "Rollout/release expectation", "What is the rollout and release strategy (flags, phases, rollback)?"),
]
DEFAULT_DESCRIPTION_SECTION_ALIASES = {
    "business_goal": ["business goal", "problem statement", "objective"],
    "personas": ["personas", "users", "target users"],
    "scope": ["scope", "in scope", "out of scope"],
    "acceptance_criteria": ["acceptance criteria", "acceptance"],
    "dependencies": ["dependencies", "constraints", "blockers"],
    "nfrs": ["non-functional requirements", "nfrs", "security/performance/compliance"],
    "success_metrics": ["success metrics", "kpi", "measurement"],
    "rollout_plan": ["rollout plan", "release plan", "rollout/release expectation"],
}
TEMPLATE_LABEL = "dor-template-shared"
STATE_LABEL_PREFIX = "orc-state-"

STATE_TRANSITIONS = {
    "NEW": ("TRIAGE", ["initial_problem_goals_constraints"]),
    "TRIAGE": ("READY FOR REFINEMENT", ["customer_contact_confirmed", "risk_level_set", "open_questions_initialized", "dor_required_items_complete"]),
    "READY FOR REFINEMENT": ("IN REFINEMENT", ["refinement_started"]),
    "IN REFINEMENT": ("READY FOR DELIVERY", ["stories_linked", "ac_measurable", "nfrs_filled_or_na", "questions_resolved_or_tracked", "design_v1_linked", "adrs_linked", "tasks_subtasks_linked", "security_review_recorded"]),
    "READY FOR DELIVERY": ("IN DELIVERY", ["delivery_run_started", "team_assigned"]),
    "IN DELIVERY": ("READY FOR RELEASE", ["ci_tests_pass", "sast_pass", "dependency_scan_pass", "secrets_scan_pass", "iac_scan_pass", "qa_evidence_linked", "security_signoff_if_medium_high"]),
    "READY FOR RELEASE": ("RELEASING", ["release_readiness_confirmed", "rollout_rollback_plan_exists"]),
    "RELEASING": ("DONE", ["release_notes_published", "runbook_updated", "deployment_evidence_linked"]),
}

# Canonical workflow status aliases.
# You can override/extend with ORCHESTRATOR_STATUS_MAP_JSON:
# {"NEW":["To Do"],"DONE":["Done"]}
DEFAULT_STATUS_ALIASES = {
    "NEW": ["NEW", "To Do"],
    "TRIAGE": ["TRIAGE", "Triage"],
    "READY FOR REFINEMENT": ["READY FOR REFINEMENT", "Ready for Refinement"],
    "IN REFINEMENT": ["IN REFINEMENT", "In Refinement"],
    "READY FOR DELIVERY": ["READY FOR DELIVERY", "Ready for Delivery"],
    "IN DELIVERY": ["IN DELIVERY", "In Delivery"],
    "READY FOR RELEASE": ["READY FOR RELEASE", "Ready for Release"],
    "RELEASING": ["RELEASING", "Releasing"],
    "DONE": ["DONE", "Done"],
}

DISPATCH_TASKS_BY_STAGE = {
    "TRIAGE": [
        ("po-requirements", "Confirm customer contact, risk level, and initialize open questions in the Epic."),
    ],
    "READY FOR REFINEMENT": [
        ("po-requirements", "Refinement kickoff: resolve all missing required items, confirm customer answers, then create the Confluence requirements page."),
    ],
    "IN REFINEMENT": [
        ("architect", "Create solution design v1 and ADR links in Confluence."),
        ("security-architect", "Run security review and record sign-off or changes requested."),
    ],
    "READY FOR DELIVERY": [
        ("devops-iac", "Prepare CI/CD, environments, IaC baseline, and policy-as-code."),
        ("developer", "Implement feature stories and unit tests with PR links."),
        ("tester-qa", "Prepare test plan and define QA evidence links."),
        ("finops", "Review cost delta, tags, and budget guardrails."),
    ],
    "IN DELIVERY": [
        ("developer", "Execute implementation tasks and attach PR/pipeline evidence."),
        ("tester-qa", "Execute e2e/regression and attach QA evidence."),
    ],
    "READY FOR RELEASE": [
        ("release-manager", "Prepare release notes and rollout/rollback runbook links."),
    ],
}

REQUIRED_ITEM_BY_ID = {item_id: (title, question) for item_id, title, question in REQUIRED_ITEMS}
REQUIRED_ITEM_ORDER = [item_id for item_id, _title, _question in REQUIRED_ITEMS]

GATE_LABELS = {
    "initial_problem_goals_constraints": "Epic has initial context (problem, goals, constraints)",
    "confluence_templates_linked": "Confluence requirement/design templates linked",
    "customer_contact_confirmed": "Customer contact confirmed (Epic creator)",
    "risk_level_set": "Risk level set (Low/Medium/High)",
    "open_questions_initialized": "Open Questions section initialized",
    "dor_required_items_complete": "All required product requirement sections are complete",
    "refinement_started": "Refinement work has started",
    "stories_linked": "Stories are created and linked to Epic",
    "ac_measurable": "Acceptance criteria are measurable",
    "nfrs_filled_or_na": "Non-functional requirements filled or marked N/A",
    "questions_resolved_or_tracked": "Questions are resolved or tracked (answers/assumptions/decisions)",
    "design_v1_linked": "Solution Design v1 linked",
    "adrs_linked": "ADRs linked",
    "tasks_subtasks_linked": "Tasks/subtasks are linked",
    "security_review_recorded": "Security review result recorded",
    "delivery_run_started": "Delivery run has started",
    "team_assigned": "Delivery team assigned",
    "ci_tests_pass": "CI tests evidence available",
    "sast_pass": "SAST evidence available",
    "dependency_scan_pass": "Dependency scan evidence available",
    "secrets_scan_pass": "Secrets scan evidence available",
    "iac_scan_pass": "IaC scan evidence available",
    "qa_evidence_linked": "QA evidence linked",
    "security_signoff_if_medium_high": "Security sign-off recorded for Medium/High risk",
    "release_readiness_confirmed": "Release readiness confirmed",
    "rollout_rollback_plan_exists": "Rollout and rollback plan documented",
    "release_notes_published": "Release notes published",
    "runbook_updated": "Runbook updated",
    "deployment_evidence_linked": "Deployment evidence linked",
    "stage_dispatch_signoff_complete": "All agent stories for current stage are signed off (Done)",
    "all_dispatch_stories_done": "All orchestrator dispatch stories are Done before Epic completion",
}


def _extract_text(node: Any) -> str:
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return " ".join(_extract_text(item) for item in node)
    if isinstance(node, dict):
        parts = []
        if "text" in node and isinstance(node["text"], str):
            parts.append(node["text"])
        for key in ("content", "attrs"):
            if key in node:
                parts.append(_extract_text(node[key]))
        # Jira payloads frequently place useful text in nested keys
        # like comment.comments[].body. Include all remaining keys.
        for key, value in node.items():
            if key not in ("text", "content", "attrs", "type", "version", "marks"):
                parts.append(_extract_text(value))
        return " ".join(parts)
    return ""


def _extract_description_text(node: Any) -> str:
    if not isinstance(node, dict):
        return _extract_text(node)
    if node.get("type") == "doc" and isinstance(node.get("content"), list):
        lines = []
        for block in node["content"]:
            line = _extract_text(block).strip()
            if line:
                lines.append(line)
        return "\n".join(lines)
    return _extract_text(node)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, str(default)).strip().lower()
    return raw in ("1", "true", "yes", "on")


def _to_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    raw = str(value).strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off", ""):
        return False
    return default


def _status_aliases() -> dict[str, list[str]]:
    aliases: dict[str, list[str]] = {k: list(v) for k, v in DEFAULT_STATUS_ALIASES.items()}
    raw = os.getenv("ORCHESTRATOR_STATUS_MAP_JSON", "").strip()
    if not raw:
        return aliases
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return aliases
    if not isinstance(parsed, dict):
        return aliases
    for canonical, values in parsed.items():
        if not isinstance(canonical, str):
            continue
        c_key = canonical.strip().upper()
        if c_key not in aliases:
            aliases[c_key] = [canonical]
        if isinstance(values, str):
            aliases[c_key].append(values)
        elif isinstance(values, list):
            aliases[c_key].extend(str(v) for v in values if isinstance(v, str))
    return aliases


def _canonical_status(status_name: str) -> str:
    raw = str(status_name or "").strip()
    if not raw:
        return ""
    raw_upper = raw.upper()
    for canonical, values in _status_aliases().items():
        for value in values:
            if str(value).strip().upper() == raw_upper:
                return canonical
    return raw_upper


def _state_label(canonical_status: str) -> str:
    return f"{STATE_LABEL_PREFIX}{_label_safe(canonical_status)}"


def _state_from_labels(labels: list[str]) -> str:
    known_states = set(DEFAULT_STATUS_ALIASES.keys()) | set(STATE_TRANSITIONS.keys()) | {"DONE", "BLOCKED"}
    for raw_label in labels:
        label = str(raw_label).strip().lower()
        if not label.startswith(STATE_LABEL_PREFIX):
            continue
        suffix = label[len(STATE_LABEL_PREFIX):]
        for state in known_states:
            if _label_safe(state) == suffix:
                return state
    return ""


def _status_candidates_from_jira(jira_status_name: str) -> list[str]:
    raw = str(jira_status_name or "").strip().upper()
    if not raw:
        return []
    out: list[str] = []
    for canonical, aliases in _status_aliases().items():
        for alias in aliases:
            if str(alias).strip().upper() == raw and canonical not in out:
                out.append(canonical)
                break
    if out:
        return out
    fallback = _canonical_status(jira_status_name)
    if fallback:
        out.append(fallback)
    return out


def _resolve_orchestrator_state(labels: list[str], jira_status_name: str) -> tuple[str, str]:
    label_state = _state_from_labels(labels)
    candidates = _status_candidates_from_jira(jira_status_name)

    if label_state and label_state in candidates:
        return label_state, "label_and_jira"
    if len(candidates) == 1:
        return candidates[0], "jira_unique"
    if label_state:
        return label_state, "label_fallback"
    if candidates:
        return candidates[0], "jira_ambiguous"
    return _canonical_status(jira_status_name), "jira_raw"


def _sync_state_label(issue_key: str, existing_labels: list[str], canonical_status: str) -> bool:
    wanted = _state_label(canonical_status)
    current_state_labels = [str(l) for l in existing_labels if str(l).startswith(STATE_LABEL_PREFIX)]
    if len(current_state_labels) == 1 and current_state_labels[0] == wanted:
        return True
    ops = [{"remove": l} for l in current_state_labels if l != wanted]
    if wanted not in current_state_labels:
        ops.append({"add": wanted})
    if not ops:
        return True
    code, _ = _jira_request(
        "PUT",
        f"/rest/api/3/issue/{issue_key}",
        body={"update": {"labels": ops}},
    )
    return code in (200, 204)


def _split_description_sections(description_text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {"general": []}
    current = "general"
    for raw_line in description_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading_match = re.match(r"^(?:#+\s*)?([A-Za-z0-9 /_-]{3,80}):\s*$", line)
        if heading_match:
            current = _norm(heading_match.group(1))
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return {k: _norm(" ".join(v)) for k, v in sections.items()}


def _load_field_map() -> dict[str, list[str]]:
    raw = os.getenv("DOR_FIELD_MAP_JSON", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    out: dict[str, list[str]] = {}
    for key, value in parsed.items():
        if isinstance(value, str):
            out[key] = [value]
        elif isinstance(value, list):
            out[key] = [str(v) for v in value if isinstance(v, str)]
    return out


def _resolve_selector(fields: dict[str, Any], description_sections: dict[str, str], selector: str) -> str:
    if selector.startswith("description_section:"):
        section = _norm(selector.split(":", 1)[1])
        return description_sections.get(section, "")
    field_name = selector.split(":", 1)[1] if selector.startswith("field:") else selector
    return _norm(_extract_text(fields.get(field_name)))


def _get_selectors(item_id: str, field_map: dict[str, list[str]]) -> list[str]:
    selectors = list(field_map.get(item_id, []))
    for alias in DEFAULT_DESCRIPTION_SECTION_ALIASES.get(item_id, []):
        selectors.append(f"description_section:{alias}")
    return selectors


def _evaluate_missing_items(epic: dict[str, Any]) -> tuple[list[tuple[str, str, str]], dict[str, str]]:
    fields = epic.get("fields", {})
    description_sections = _split_description_sections(_extract_description_text(fields.get("description")))
    field_map = _load_field_map()
    missing = []
    evidence: dict[str, str] = {}
    for item_id, title, question in REQUIRED_ITEMS:
        found = ""
        found_selector = ""
        for selector in _get_selectors(item_id, field_map):
            resolved = _resolve_selector(fields, description_sections, selector)
            if resolved:
                found = resolved
                found_selector = selector
                break
        if not found:
            missing.append((item_id, title, question))
        else:
            evidence[item_id] = found_selector
    return missing, evidence


def _required_items_snapshot(epic: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    fields = epic.get("fields", {})
    description_sections = _split_description_sections(_extract_description_text(fields.get("description")))
    field_map = _load_field_map()
    values: dict[str, str] = {}
    missing_ids: list[str] = []
    for item_id, _title, _question in REQUIRED_ITEMS:
        found = ""
        for selector in _get_selectors(item_id, field_map):
            resolved = _resolve_selector(fields, description_sections, selector)
            if resolved:
                found = resolved
                break
        if found:
            values[item_id] = found
        else:
            missing_ids.append(item_id)
    return values, missing_ids


def _required_item_label(item_id: str) -> str:
    title, _question = REQUIRED_ITEM_BY_ID.get(item_id, (item_id.replace("_", " "), ""))
    return title


def _required_item_question(item_id: str) -> str:
    _title, question = REQUIRED_ITEM_BY_ID.get(item_id, ("", "Please provide this information."))
    return question


def _gate_label(gate_id: str) -> str:
    return GATE_LABELS.get(gate_id, gate_id.replace("_", " "))


def _build_comment(missing: list[tuple[str, str, str]]) -> str:
    lines = ["Epic Readiness Review: Not Ready for Delivery", "", "Missing information:"]
    for idx, (_, title, question) in enumerate(missing, 1):
        lines.append(f"{idx}. {title}: {question}")
    lines.append("")
    lines.append("Please update this Epic and I will re-check automatically.")
    return "\n".join(lines)


def _build_template_comment() -> str:
    return "\n".join(
        [
            "Epic Readiness Review: Please use this template",
            "",
            "Business Goal:",
            "Personas:",
            "Scope:",
            "Acceptance Criteria:",
            "Dependencies:",
            "Non-Functional Requirements:",
            "Success Metrics:",
            "Rollout Plan:",
            "",
            "Please fill each section so the Epic can be marked ready for delivery.",
        ]
    )


def _parse_jira_datetime(value: str) -> datetime | None:
    if not value:
        return None
    for pattern in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(value, pattern)
        except ValueError:
            continue
    return None


def _latest_agent_comment(comments: list[dict[str, Any]]) -> datetime | None:
    latest = None
    for comment in comments:
        text = _extract_text(comment.get("body", ""))
        if "[dor-hash:" not in text:
            continue
        created = _parse_jira_datetime(str(comment.get("created", "")))
        if created is None:
            continue
        if latest is None or created > latest:
            latest = created
    return latest


def _has_customer_response_after_agent(comments: list[dict[str, Any]], latest_agent_time: datetime | None) -> bool:
    if latest_agent_time is None:
        return False
    for comment in comments:
        created = _parse_jira_datetime(str(comment.get("created", "")))
        if created is None or created <= latest_agent_time:
            continue
        if "[dor-hash:" in _extract_text(comment.get("body", "")):
            continue
        return True
    return False


def _cooldown_decision(comments: list[dict[str, Any]], cooldown_hours: int) -> tuple[bool, str | None, bool]:
    latest = _latest_agent_comment(comments)
    if latest is None:
        return True, None, False
    if _has_customer_response_after_agent(comments, latest):
        return False, None, True
    cooldown_until = latest.astimezone(timezone.utc) + timedelta(hours=cooldown_hours)
    if datetime.now(timezone.utc) < cooldown_until:
        return False, cooldown_until.isoformat(), False
    return True, None, False


def _should_share_template(epic: dict[str, Any], missing_count: int) -> bool:
    if not _env_bool("ENABLE_TEMPLATE_HINT", True) or missing_count == 0:
        return False
    fields = epic.get("fields", {})
    labels = fields.get("labels", [])
    if isinstance(labels, list) and TEMPLATE_LABEL in labels:
        return False
    description_text = _extract_description_text(fields.get("description"))
    sections = _split_description_sections(description_text)
    structured_count = len([k for k, v in sections.items() if k != "general" and v])
    return structured_count < 3 or len(description_text.strip()) < 120


def _jira_auth_header() -> str:
    email = os.getenv("JIRA_EMAIL", "").strip()
    token = os.getenv("JIRA_API_TOKEN", "").strip()
    if not email or not token:
        return ""
    basic = base64.b64encode(f"{email}:{token}".encode("utf-8")).decode("utf-8")
    return f"Basic {basic}"


def _atlassian_basic_auth() -> str:
    email = os.getenv("JIRA_EMAIL", "").strip()
    token = os.getenv("JIRA_API_TOKEN", "").strip()
    if not email or not token:
        return ""
    basic = base64.b64encode(f"{email}:{token}".encode("utf-8")).decode("utf-8")
    return f"Basic {basic}"


def _jira_request(method: str, path: str, query: dict[str, str] | None = None, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    base = os.getenv("JIRA_BASE_URL", "").rstrip("/")
    auth = _jira_auth_header()
    if not base or not auth:
        return 500, {"error": "JIRA_BASE_URL/JIRA_EMAIL/JIRA_API_TOKEN app settings are required"}
    url = f"{base}{path}"
    if query:
        url = f"{url}?{parse.urlencode(query)}"
    headers = {"Authorization": auth, "Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    req = request.Request(url=url, method=method, headers=headers, data=data)
    try:
        with request.urlopen(req, timeout=25) as resp:
            payload = resp.read().decode("utf-8")
            return resp.status, json.loads(payload) if payload else {}
    except Exception as ex:  # pragma: no cover
        return 500, {"error": str(ex)}


def _confluence_request(method: str, path: str, query: dict[str, str] | None = None, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    base = os.getenv("JIRA_BASE_URL", "").rstrip("/")
    auth = _atlassian_basic_auth()
    if not base or not auth:
        return 500, {"error": "JIRA_BASE_URL/JIRA_EMAIL/JIRA_API_TOKEN app settings are required"}
    url = f"{base}/wiki{path}"
    if query:
        url = f"{url}?{parse.urlencode(query)}"
    headers = {"Authorization": auth, "Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    req = request.Request(url=url, method=method, headers=headers, data=data)
    try:
        with request.urlopen(req, timeout=25) as resp:
            payload = resp.read().decode("utf-8")
            return resp.status, json.loads(payload) if payload else {}
    except Exception as ex:  # pragma: no cover
        return 500, {"error": str(ex)}


def _confluence_space_key() -> str:
    return os.getenv("CONFLUENCE_SPACE_KEY", "").strip()


def _confluence_page_url(content_id: str) -> str:
    base = os.getenv("JIRA_BASE_URL", "").rstrip("/")
    return f"{base}/wiki/spaces/{_confluence_space_key()}/pages/{content_id}"


def _confluence_create_page(title: str, storage_html: str) -> tuple[bool, str | None]:
    space_key = _confluence_space_key()
    if not space_key:
        return False, None
    payload = {
        "type": "page",
        "title": title,
        "space": {"key": space_key},
        "body": {
            "storage": {
                "value": storage_html,
                "representation": "storage",
            }
        },
    }
    code, data = _confluence_request("POST", "/rest/api/content", body=payload)
    if code not in (200, 201):
        return False, None
    cid = str(data.get("id", ""))
    if not cid:
        return False, None
    return True, _confluence_page_url(cid)


def _issue_has_marker(issue_key: str, marker: str) -> bool:
    code, data = _jira_request("GET", f"/rest/api/3/issue/{issue_key}", query={"fields": "comment"})
    if code != 200:
        return False
    comments = data.get("fields", {}).get("comment", {}).get("comments", [])
    text = _extract_text(comments)
    return marker in text


def _security_review_gaps(req_values: dict[str, str]) -> list[str]:
    gaps: list[str] = []
    must_have = [
        ("business_goal", "Business goal/problem statement is missing in Epic requirements."),
        ("personas", "Personas are missing in Epic requirements."),
        ("scope", "Scope boundaries are missing in Epic requirements."),
        ("nfrs", "Non-functional requirements are missing in Epic requirements."),
        ("dependencies", "Dependencies/constraints are missing in Epic requirements."),
        ("success_metrics", "Success metrics are missing in Epic requirements."),
        ("rollout_plan", "Rollout plan is missing in Epic requirements."),
    ]
    for key, msg in must_have:
        value = _norm(req_values.get(key, ""))
        if not value or value == "tbd":
            gaps.append(msg)

    nfr = _norm(req_values.get("nfrs", ""))
    if nfr and "security" not in nfr and "compliance" not in nfr:
        gaps.append("NFRs do not explicitly mention security/compliance expectations.")
    return gaps


def _auto_execute_architect_security(epic_key: str, epic_summary: str, architect_issue_key: str, security_issue_key: str) -> tuple[bool, str]:
    approved_marker = "[arch-sec-auto-v2-approved]"
    changes_marker = "[arch-sec-auto-v2-changes]"
    if _issue_has_marker(architect_issue_key, approved_marker) and _issue_has_marker(security_issue_key, approved_marker):
        return True, "already_executed"
    if _issue_has_marker(architect_issue_key, changes_marker) and _issue_has_marker(security_issue_key, changes_marker):
        return False, "changes_requested_pending"

    if not _confluence_space_key():
        msg = (
            "Automated architect/security execution blocked: CONFLUENCE_SPACE_KEY is not configured.\n"
            "Set CONFLUENCE_SPACE_KEY in Function app settings to enable Confluence documentation automation."
        )
        _jira_request("POST", f"/rest/api/3/issue/{architect_issue_key}/comment", body={"body": _adf_text_body(msg)})
        _jira_request("POST", f"/rest/api/3/issue/{security_issue_key}/comment", body={"body": _adf_text_body(msg)})
        return False, "missing_confluence_space_key"

    epic_code, epic_data = _jira_request("GET", f"/rest/api/3/issue/{epic_key}", query={"fields": "description"})
    req_values: dict[str, str] = {}
    if epic_code == 200:
        req_values, _ = _required_items_snapshot(epic_data)

    def req(item_id: str, fallback: str = "TBD") -> str:
        return req_values.get(item_id, fallback)

    title_prefix = f"[{epic_key}]"
    ok_design, design_url = _confluence_create_page(
        f"{title_prefix} Solution Design v1",
        (
            "<h1>Solution Design v1</h1>"
            f"<p><strong>Epic:</strong> {epic_key}</p>"
            f"<p><strong>Summary:</strong> {epic_summary}</p>"
            "<h2>Context</h2>"
            f"<p>{req('business_goal')}</p>"
            "<h2>Users/Personas</h2>"
            f"<p>{req('personas')}</p>"
            "<h2>Scope</h2>"
            f"<p>{req('scope')}</p>"
            "<h2>Functional Design</h2>"
            "<ul>"
            "<li>Server-rendered web flow for shopping lists and items</li>"
            "<li>In-memory storage for MVP speed/cost</li>"
            "<li>Reset workflow for demo data</li>"
            "</ul>"
            "<h2>Architecture Components</h2>"
            "<ul>"
            "<li>Web UI: server-rendered pages for list and item actions</li>"
            "<li>Application Service: Spring Boot app exposing HTTP endpoints</li>"
            "<li>Domain Layer: shopping list and item lifecycle rules</li>"
            "<li>Storage Layer (MVP): in-memory repository with reset seed data</li>"
            "<li>Observability: application logs and health endpoint</li>"
            "</ul>"
            "<h2>API/Route Contract</h2>"
            "<ul>"
            "<li>GET / : list all shopping lists with item counts</li>"
            "<li>POST /lists : create shopping list</li>"
            "<li>POST /lists/{id}/delete : delete shopping list</li>"
            "<li>GET /lists/{id} : open list details</li>"
            "<li>POST /lists/{id}/items : add item</li>"
            "<li>POST /lists/{id}/items/{itemId}/delete : remove item</li>"
            "<li>POST /reset : restore demo seed data</li>"
            "</ul>"
            "<h2>Non-Functional Requirements</h2>"
            f"<p>{req('nfrs')}</p>"
            "<h2>Dependencies & Constraints</h2>"
            f"<p>{req('dependencies')}</p>"
            "<h2>Deployment Topology</h2>"
            "<ul>"
            "<li>Runtime: single Spring Boot service (JAR) for MVP</li>"
            "<li>Environments: dev, test, prod with config separation</li>"
            "<li>Config/Secrets: environment variables + Key Vault references</li>"
            "</ul>"
            "<h2>CI/CD Blueprint (DevOps Implementation Input)</h2>"
            "<ol>"
            "<li>Trigger: PR to main branch and merge to main</li>"
            "<li>Build: Maven clean verify, artifact packaging</li>"
            "<li>Quality Gates: unit tests, SAST, dependency scan, secrets scan</li>"
            "<li>Artifact: versioned JAR publication</li>"
            "<li>Deploy Dev/Test: automated deployment with smoke tests</li>"
            "<li>Deploy Prod: approval gate + rollout + rollback path</li>"
            "</ol>"
            "<h2>Pipeline Variables and Secrets</h2>"
            "<ul>"
            "<li>APP_ENV, JAVA_VERSION, ARTIFACT_VERSION</li>"
            "<li>Key Vault references for runtime secrets and tokens</li>"
            "<li>No hardcoded secrets in repo or pipeline YAML</li>"
            "</ul>"
            "<h2>Operational Runbook Inputs</h2>"
            "<ul>"
            "<li>Health check endpoint and expected response</li>"
            "<li>Rollback to previous artifact version</li>"
            "<li>Known MVP limits: in-memory persistence and single-instance assumptions</li>"
            "</ul>"
            "<h2>Success Metrics</h2>"
            f"<p>{req('success_metrics')}</p>"
            "<h2>Rollout Plan</h2>"
            f"<p>{req('rollout_plan')}</p>"
            "<h2>Definition of Done Mapping</h2>"
            "<ul>"
            "<li>Architecture approved by Security Architect</li>"
            "<li>Design provides CI/CD-ready deployment and gating instructions</li>"
            "<li>All delivery artifacts reference Epic key</li>"
            "</ul>"
            "<h2>Traceability</h2>"
            f"<p>All delivery artifacts must reference Epic key <strong>{epic_key}</strong>.</p>"
            "<p>Created by Architect AI agent.</p>"
        ),
    )
    ok_adr, adr_url = _confluence_create_page(
        f"{title_prefix} ADR-001 In-Memory MVP Decision",
        (
            "<h1>ADR-001: In-Memory Storage for MVP</h1>"
            "<h2>Status</h2><p>Accepted</p>"
            "<h2>Context</h2><p>MVP target is fast, low-cost delivery for demo scenarios.</p>"
            "<h2>Decision</h2><p>Use in-memory persistence for shopping lists/items in MVP.</p>"
            "<h2>Consequences</h2>"
            "<ul>"
            "<li>Pros: fast implementation, no DB cost/ops overhead.</li>"
            "<li>Cons: no persistence between restarts; not suitable for production multi-user use.</li>"
            "</ul>"
            f"<p><strong>Epic:</strong> {epic_key}</p>"
        ),
    )
    ok_sec, sec_url = _confluence_create_page(
        f"{title_prefix} Security Review",
        (
            "<h1>Security Review</h1>"
            f"<p><strong>Epic:</strong> {epic_key}</p>"
            "<h2>Threat Model (Light)</h2>"
            "<ul>"
            "<li>Input validation for list/item fields</li>"
            "<li>No sensitive data storage in MVP</li>"
            "<li>No authentication in MVP scope (accepted for demo use)</li>"
            "</ul>"
            "<h2>Required Controls</h2>"
            "<ul>"
            "<li>Dependency scan in CI</li>"
            "<li>Secrets scan in CI</li>"
            "<li>Basic SAST check in CI</li>"
            "</ul>"
            "<h2>Decision</h2><p>Approved for demo scope. Re-review required if scope/risk increases.</p>"
        ),
    )
    if not (ok_design and ok_adr and ok_sec and design_url and adr_url and sec_url):
        return False, "confluence_page_create_failed"

    gaps = _security_review_gaps(req_values)
    if gaps:
        security_comment = "\n".join(
            [
                "Security Architect AI review result: CHANGES REQUESTED.",
                f"- Reviewed design: {design_url}",
                f"- Reviewed ADR: {adr_url}",
                f"- Security review page: {sec_url}",
                "",
                "Security gaps to be addressed by Architect AI:",
                *[f"- {g}" for g in gaps],
                "",
                "Architect AI: please update the solution design and reply in this story for re-review.",
                changes_marker,
            ]
        )
        architect_comment = "\n".join(
            [
                "Security Architect AI requested changes to Solution Design.",
                f"- Design page: {design_url}",
                f"- ADR page: {adr_url}",
                f"- Security review page: {sec_url}",
                "",
                "Required updates:",
                *[f"- {g}" for g in gaps],
                "",
                "After update, comment in this issue and request security re-review.",
                changes_marker,
            ]
        )
        epic_comment = "\n".join(
            [
                "Architect/Security handoff: security changes requested.",
                f"- Architect design: {design_url}",
                f"- ADR: {adr_url}",
                f"- Security review: {sec_url}",
                "Epic is blocked at design-security gate until gaps are resolved.",
                changes_marker,
            ]
        )
        _jira_request("POST", f"/rest/api/3/issue/{security_issue_key}/comment", body={"body": _adf_text_body(security_comment)})
        _jira_request("POST", f"/rest/api/3/issue/{architect_issue_key}/comment", body={"body": _adf_text_body(architect_comment)})
        _jira_request("POST", f"/rest/api/3/issue/{epic_key}/comment", body={"body": _adf_text_body(epic_comment)})
        return False, "security_changes_requested"

    architect_comment = "\n".join(
        [
            "Architect AI agent completed documentation and requested Security AI review.",
            f"- Solution Design v1: {design_url}",
            f"- ADR-001: {adr_url}",
            f"- Security review request issue: {security_issue_key}",
            "",
            "Security AI sign-off received. Architect AI sign-off: Approved for next stage.",
            approved_marker,
        ]
    )
    security_comment = "\n".join(
        [
            "Security Architect AI agent reviewed architect outputs and documented security decision.",
            f"- Reviewed design: {design_url}",
            f"- Reviewed ADR: {adr_url}",
            f"- Security review page: {sec_url}",
            "",
            "Decision: Approved. Security AI sign-off complete and communicated to Architect AI.",
            approved_marker,
        ]
    )
    epic_comment = "\n".join(
        [
            "Automated architect/security handoff complete (AI-to-AI).",
            f"- Architect documentation: {design_url}",
            f"- ADR: {adr_url}",
            f"- Security review/sign-off: {sec_url}",
            "Both Architect and Security agents signed off for next stage.",
            approved_marker,
        ]
    )
    _jira_request("POST", f"/rest/api/3/issue/{architect_issue_key}/comment", body={"body": _adf_text_body(architect_comment)})
    _jira_request("POST", f"/rest/api/3/issue/{security_issue_key}/comment", body={"body": _adf_text_body(security_comment)})
    _jira_request("POST", f"/rest/api/3/issue/{epic_key}/comment", body={"body": _adf_text_body(epic_comment)})

    _transition_issue(architect_issue_key, "DONE")
    _transition_issue(security_issue_key, "DONE")
    return True, "completed"


def _auto_execute_devops_iac(epic_key: str, epic_summary: str, devops_issue_key: str, branch_url: str | None, pr_url: str | None) -> tuple[bool, str]:
    marker = "[devops-auto-v1]"
    if _issue_has_marker(devops_issue_key, marker):
        return True, "already_executed"

    if not _confluence_space_key():
        msg = (
            "Automated DevOps execution blocked: CONFLUENCE_SPACE_KEY is not configured.\n"
            "Set CONFLUENCE_SPACE_KEY in Function app settings to enable Confluence documentation automation."
        )
        _jira_request("POST", f"/rest/api/3/issue/{devops_issue_key}/comment", body={"body": _adf_text_body(msg)})
        return False, "missing_confluence_space_key"

    title = f"[{epic_key}] DevOps Delivery Plan"
    ok_plan, plan_url = _confluence_create_page(
        title,
        (
            "<h1>DevOps Delivery Plan</h1>"
            f"<p><strong>Epic:</strong> {epic_key}</p>"
            f"<p><strong>Summary:</strong> {epic_summary}</p>"
            "<h2>Pipeline Stages</h2>"
            "<ol>"
            "<li>Validate: lint + unit tests</li>"
            "<li>Security gates: SAST + dependency + secrets + IaC scans</li>"
            "<li>Package: build versioned artifact</li>"
            "<li>Deploy Dev/Test: smoke tests</li>"
            "<li>Deploy Prod: approval gate + rollback path</li>"
            "</ol>"
            "<h2>Environment Strategy</h2>"
            "<ul>"
            "<li>Separate dev/test/prod configuration</li>"
            "<li>Secrets from Key Vault references only</li>"
            "<li>No hardcoded credentials in repository</li>"
            "</ul>"
            "<h2>Operational Controls</h2>"
            "<ul>"
            "<li>Health endpoint check after deployment</li>"
            "<li>Rollback to previous artifact version</li>"
            "<li>Release evidence links tracked in Epic</li>"
            "</ul>"
            "<h2>Bitbucket Delivery Artifacts</h2>"
            f"<p>Branch: {branch_url or 'N/A'}</p>"
            f"<p>Pull request: {pr_url or 'N/A'}</p>"
        ),
    )
    if not (ok_plan and plan_url):
        return False, "confluence_page_create_failed"

    devops_comment = "\n".join(
        [
            "DevOps/IaC AI agent completed delivery setup plan.",
            f"- DevOps plan: {plan_url}",
            f"- Bitbucket branch: {branch_url or 'N/A'}",
            f"- Bitbucket PR: {pr_url or 'N/A'}",
            "",
            "DevOps sign-off: CI/CD baseline, environments, and rollout/rollback controls documented.",
            marker,
        ]
    )
    epic_comment = "\n".join(
        [
            "DevOps/IaC AI handoff complete.",
            f"- DevOps delivery plan: {plan_url}",
            f"- Bitbucket branch: {branch_url or 'N/A'}",
            f"- Bitbucket PR: {pr_url or 'N/A'}",
            marker,
        ]
    )
    _jira_request("POST", f"/rest/api/3/issue/{devops_issue_key}/comment", body={"body": _adf_text_body(devops_comment)})
    _jira_request("POST", f"/rest/api/3/issue/{epic_key}/comment", body={"body": _adf_text_body(epic_comment)})
    _transition_issue(devops_issue_key, "DONE")
    return True, "completed"


def _auto_execute_developer(epic_key: str, epic_summary: str, developer_issue_key: str, branch_url: str | None, pr_url: str | None) -> tuple[bool, str]:
    marker = "[developer-auto-v1]"
    if _issue_has_marker(developer_issue_key, marker):
        return True, "already_executed"
    if not _confluence_space_key():
        return False, "missing_confluence_space_key"

    ok_page, page_url = _confluence_create_page(
        f"[{epic_key}] Implementation Plan",
        (
            "<h1>Implementation Plan</h1>"
            f"<p><strong>Epic:</strong> {epic_key}</p>"
            f"<p><strong>Summary:</strong> {epic_summary}</p>"
            "<h2>Implementation Scope</h2>"
            "<ul>"
            "<li>Implement shopping list and item flows based on acceptance criteria</li>"
            "<li>Add/adjust unit tests for core service logic and web routes</li>"
            "<li>Ensure all changes keep MVP constraints and performance targets</li>"
            "</ul>"
            "<h2>Code Delivery Plan</h2>"
            "<ol>"
            "<li>Create/update feature branch and link story key in commits</li>"
            "<li>Open PR with test evidence</li>"
            "<li>Address review feedback and merge readiness checks</li>"
            "</ol>"
            "<h2>Delivery Evidence</h2>"
            f"<p>Branch: {branch_url or 'N/A'}</p>"
            f"<p>PR: {pr_url or 'N/A'}</p>"
        ),
    )
    if not (ok_page and page_url):
        return False, "confluence_page_create_failed"

    issue_comment = "\n".join(
        [
            "Developer AI agent completed implementation planning and delivery evidence update.",
            f"- Implementation plan: {page_url}",
            f"- Branch: {branch_url or 'N/A'}",
            f"- PR: {pr_url or 'N/A'}",
            marker,
        ]
    )
    _jira_request("POST", f"/rest/api/3/issue/{developer_issue_key}/comment", body={"body": _adf_text_body(issue_comment)})
    _transition_issue(developer_issue_key, "DONE")
    return True, "completed"


def _auto_execute_tester_qa(epic_key: str, epic_summary: str, tester_issue_key: str) -> tuple[bool, str]:
    marker = "[tester-auto-v1]"
    if _issue_has_marker(tester_issue_key, marker):
        return True, "already_executed"
    if not _confluence_space_key():
        return False, "missing_confluence_space_key"

    ok_page, page_url = _confluence_create_page(
        f"[{epic_key}] QA Test Plan",
        (
            "<h1>QA Test Plan</h1>"
            f"<p><strong>Epic:</strong> {epic_key}</p>"
            f"<p><strong>Summary:</strong> {epic_summary}</p>"
            "<h2>Functional Scenarios</h2>"
            "<ul>"
            "<li>Create shopping list</li>"
            "<li>Delete shopping list</li>"
            "<li>Add item to list</li>"
            "<li>Remove item from list</li>"
            "<li>Reset demo data</li>"
            "</ul>"
            "<h2>Quality Gates</h2>"
            "<ul>"
            "<li>Smoke tests pass on deployed build</li>"
            "<li>No critical regression in MVP user journey</li>"
            "<li>Evidence links attached to Epic and story</li>"
            "</ul>"
        ),
    )
    if not (ok_page and page_url):
        return False, "confluence_page_create_failed"

    issue_comment = "\n".join(
        [
            "Tester/QA AI agent completed test planning.",
            f"- QA plan: {page_url}",
            marker,
        ]
    )
    _jira_request("POST", f"/rest/api/3/issue/{tester_issue_key}/comment", body={"body": _adf_text_body(issue_comment)})
    _transition_issue(tester_issue_key, "DONE")
    return True, "completed"


def _auto_execute_finops(epic_key: str, epic_summary: str, finops_issue_key: str) -> tuple[bool, str]:
    marker = "[finops-auto-v1]"
    if _issue_has_marker(finops_issue_key, marker):
        return True, "already_executed"
    if not _confluence_space_key():
        return False, "missing_confluence_space_key"

    ok_page, page_url = _confluence_create_page(
        f"[{epic_key}] FinOps Review",
        (
            "<h1>FinOps Review</h1>"
            f"<p><strong>Epic:</strong> {epic_key}</p>"
            f"<p><strong>Summary:</strong> {epic_summary}</p>"
            "<h2>Cost Baseline</h2>"
            "<ul>"
            "<li>MVP uses low-cost architecture (single app service, in-memory storage)</li>"
            "<li>No database/storage growth costs for MVP phase</li>"
            "</ul>"
            "<h2>Tagging and Governance</h2>"
            "<ul>"
            "<li>Recommend tags: application, environment, owner, cost-center</li>"
            "<li>Enable budget alerts for non-prod and prod scopes</li>"
            "</ul>"
            "<h2>Decision</h2>"
            "<p>No budget exception required for current MVP scope.</p>"
        ),
    )
    if not (ok_page and page_url):
        return False, "confluence_page_create_failed"

    issue_comment = "\n".join(
        [
            "FinOps AI agent completed cost and governance review.",
            f"- FinOps review: {page_url}",
            marker,
        ]
    )
    _jira_request("POST", f"/rest/api/3/issue/{finops_issue_key}/comment", body={"body": _adf_text_body(issue_comment)})
    _transition_issue(finops_issue_key, "DONE")
    return True, "completed"


def _auto_execute_release_manager(epic_key: str, epic_summary: str, release_issue_key: str) -> tuple[bool, str]:
    marker = "[release-auto-v1]"
    if _issue_has_marker(release_issue_key, marker):
        return True, "already_executed"
    if not _confluence_space_key():
        return False, "missing_confluence_space_key"

    ok_page, page_url = _confluence_create_page(
        f"[{epic_key}] Release Readiness Package",
        (
            "<h1>Release Readiness Package</h1>"
            f"<p><strong>Epic:</strong> {epic_key}</p>"
            f"<p><strong>Summary:</strong> {epic_summary}</p>"
            "<h2>Release Readiness</h2>"
            "<ul>"
            "<li>Scope and acceptance criteria validated for release candidate</li>"
            "<li>Quality and security evidence linked in Epic/story comments</li>"
            "<li>Rollback strategy confirmed</li>"
            "</ul>"
            "<h2>Release Notes</h2>"
            "<p>Release notes prepared for MVP shopping-list delivery scope.</p>"
            "<h2>Rollout Plan</h2>"
            "<ul>"
            "<li>Deploy to dev/test with smoke checks</li>"
            "<li>Approve and deploy to production</li>"
            "<li>Monitor health and user journey after deployment</li>"
            "</ul>"
            "<h2>Rollback Runbook</h2>"
            "<ul>"
            "<li>Rollback to previous artifact version</li>"
            "<li>Verify health endpoint and core flow</li>"
            "<li>Communicate rollback status in release channel</li>"
            "</ul>"
            "<h2>Deployment Evidence</h2>"
            "<p>Deployment evidence linked in Epic once pipeline execution is completed.</p>"
        ),
    )
    if not (ok_page and page_url):
        return False, "confluence_page_create_failed"

    issue_comment = "\n".join(
        [
            "Release Manager AI agent completed release-readiness package.",
            f"- Release package: {page_url}",
            "Release notes, rollout/rollback plan, and runbook are documented.",
            marker,
        ]
    )
    epic_comment = "\n".join(
        [
            "Release readiness artifacts prepared by Release Manager AI.",
            f"- Release package: {page_url}",
            marker,
        ]
    )
    _jira_request("POST", f"/rest/api/3/issue/{release_issue_key}/comment", body={"body": _adf_text_body(issue_comment)})
    _jira_request("POST", f"/rest/api/3/issue/{epic_key}/comment", body={"body": _adf_text_body(epic_comment)})
    _transition_issue(release_issue_key, "DONE")
    return True, "completed"


def _bitbucket_enabled() -> bool:
    return _env_bool("BITBUCKET_ENABLE_AUTOMATION", False)


def _bitbucket_auth_header() -> str:
    token = os.getenv("BITBUCKET_API_TOKEN", "").strip()
    if token:
        # Bitbucket API tokens authenticate via Basic(email:token).
        email = os.getenv("BITBUCKET_EMAIL", "").strip() or os.getenv("JIRA_EMAIL", "").strip()
        if email:
            basic = base64.b64encode(f"{email}:{token}".encode("utf-8")).decode("utf-8")
            return f"Basic {basic}"
        # Fallback for environments that intentionally use bearer semantics.
        return f"Bearer {token}"

    # Legacy fallback (deprecated by Bitbucket in favor of API tokens).
    user = os.getenv("BITBUCKET_USERNAME", "").strip()
    password = os.getenv("BITBUCKET_APP_PASSWORD", "").strip()
    if user and password:
        basic = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("utf-8")
        return f"Basic {basic}"
    return ""


def _bitbucket_request(method: str, path: str, query: dict[str, str] | None = None, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    base = os.getenv("BITBUCKET_API_BASE", "https://api.bitbucket.org/2.0").rstrip("/")
    auth = _bitbucket_auth_header()
    if not auth:
        return 500, {"error": "BITBUCKET_API_TOKEN is required (legacy BITBUCKET_USERNAME/BITBUCKET_APP_PASSWORD still supported)"}
    url = f"{base}{path}"
    if query:
        url = f"{url}?{parse.urlencode(query)}"
    headers = {"Authorization": auth, "Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    req = request.Request(url=url, method=method, headers=headers, data=data)
    try:
        with request.urlopen(req, timeout=25) as resp:
            payload = resp.read().decode("utf-8")
            return resp.status, json.loads(payload) if payload else {}
    except Exception as ex:  # pragma: no cover
        return 500, {"error": str(ex)}


def _bitbucket_branch_name(issue_key: str, role: str) -> str:
    role_part = _label_safe(role)[:24]
    return f"feature/{issue_key.lower()}-{role_part}"


def _jira_add_label(issue_key: str, label: str) -> bool:
    code, _ = _jira_request(
        "PUT",
        f"/rest/api/3/issue/{issue_key}",
        body={"update": {"labels": [{"add": label}]}}
    )
    return code in (200, 204)


def _repo_slug_from_labels(labels: list[str]) -> str | None:
    for label in labels:
        l = str(label).strip().lower()
        if l.startswith("repo-") and len(l) > 5:
            return l[5:]
    return None


def _repo_slug_from_text(text: str) -> str | None:
    m = re.search(r"(?:repo(?:sitory)?\s*[:=]\s*)([a-z0-9._-]{3,80})", _norm(text))
    if m:
        return m.group(1)
    return None


def _default_repo_slug(epic_key: str, epic_summary: str) -> str:
    base = _label_safe(epic_summary)[:48].strip("-")
    if not base:
        base = _label_safe(epic_key)
    return f"{base}-{_label_safe(epic_key)}"[:62].strip("-")


def _bitbucket_main_hash(workspace: str, repo: str, main_branch: str) -> str | None:
    code, data = _bitbucket_request("GET", f"/repositories/{workspace}/{repo}/refs/branches/{main_branch}")
    if code != 200:
        return None
    return str(data.get("target", {}).get("hash", "")) or None


def _bitbucket_repo_exists(workspace: str, repo: str) -> tuple[bool, str | None]:
    code, data = _bitbucket_request("GET", f"/repositories/{workspace}/{repo}")
    if code != 200:
        return False, None
    return True, str(data.get("links", {}).get("html", {}).get("href", ""))


def _bitbucket_create_repo(workspace: str, repo: str) -> tuple[bool, str | None]:
    payload: dict[str, Any] = {"scm": "git", "is_private": True}
    project_key = os.getenv("BITBUCKET_PROJECT_KEY", "").strip()
    if project_key:
        payload["project"] = {"key": project_key}
    code, data = _bitbucket_request("POST", f"/repositories/{workspace}/{repo}", body=payload)
    if code not in (200, 201):
        return False, None
    return True, str(data.get("links", {}).get("html", {}).get("href", ""))


def _bitbucket_resolve_repo_for_epic(epic_key: str, epic_summary: str, fields: dict[str, Any]) -> tuple[str | None, str | None]:
    workspace = os.getenv("BITBUCKET_WORKSPACE", "").strip()
    if not workspace:
        return None, None

    labels = fields.get("labels", [])
    labels = labels if isinstance(labels, list) else []
    from_label = _repo_slug_from_labels([str(x) for x in labels])
    if from_label:
        ok, repo_url = _bitbucket_repo_exists(workspace, from_label)
        if ok:
            return from_label, repo_url

    combined = f"{_extract_description_text(fields.get('description'))}\n{_extract_text(fields.get('comment', {}))}"
    from_text = _repo_slug_from_text(combined)
    if from_text:
        ok, repo_url = _bitbucket_repo_exists(workspace, from_text)
        if ok:
            return from_text, repo_url

    fixed_repo = os.getenv("BITBUCKET_REPO_SLUG", "").strip()
    if fixed_repo and _env_bool("BITBUCKET_SINGLE_REPO_MODE", False):
        ok, repo_url = _bitbucket_repo_exists(workspace, fixed_repo)
        if ok:
            return fixed_repo, repo_url

    if not _env_bool("BITBUCKET_AUTO_CREATE_REPO", True):
        return None, None

    candidate = from_text or fixed_repo or _default_repo_slug(epic_key, epic_summary)
    ok, repo_url = _bitbucket_repo_exists(workspace, candidate)
    if not ok:
        ok, repo_url = _bitbucket_create_repo(workspace, candidate)
        if not ok:
            return None, None
    _jira_add_label(epic_key, f"repo-{candidate}")
    _jira_request(
        "POST",
        f"/rest/api/3/issue/{epic_key}/comment",
        body={"body": _adf_text_body(f"Repository selected for this app: {candidate}\nRepo URL: {repo_url}")},
    )
    return candidate, repo_url


def _bitbucket_ensure_branch(workspace: str, repo: str, branch_name: str, main_branch: str) -> tuple[bool, str | None]:
    code, existing = _bitbucket_request("GET", f"/repositories/{workspace}/{repo}/refs/branches/{parse.quote(branch_name, safe='')}")
    if code == 200:
        return True, str(existing.get("links", {}).get("html", {}).get("href", ""))

    main_hash = _bitbucket_main_hash(workspace, repo, main_branch)
    if not main_hash:
        return False, None
    payload = {"name": branch_name, "target": {"hash": main_hash}}
    code, created = _bitbucket_request("POST", f"/repositories/{workspace}/{repo}/refs/branches", body=payload)
    if code not in (200, 201):
        return False, None
    return True, str(created.get("links", {}).get("html", {}).get("href", ""))


def _bitbucket_find_open_pr(workspace: str, repo: str, branch_name: str) -> str | None:
    q = f'source.branch.name="{branch_name}" AND state="OPEN"'
    code, data = _bitbucket_request("GET", f"/repositories/{workspace}/{repo}/pullrequests", query={"q": q, "pagelen": "1"})
    if code != 200:
        return None
    values = data.get("values", [])
    if not values:
        return None
    return str(values[0].get("links", {}).get("html", {}).get("href", "")) or None


def _bitbucket_create_pr(workspace: str, repo: str, branch_name: str, target_branch: str, epic_key: str, story_key: str, role: str) -> tuple[bool, str | None]:
    existing = _bitbucket_find_open_pr(workspace, repo, branch_name)
    if existing:
        return True, existing

    title = f"[{epic_key}] [{story_key}] {role} delivery changes"
    description = (
        f"Auto-created by orchestrator.\n\n"
        f"Epic: {epic_key}\n"
        f"Story: {story_key}\n"
        f"Role: {role}\n"
    )
    payload = {
        "title": title,
        "description": description,
        "source": {"branch": {"name": branch_name}},
        "destination": {"branch": {"name": target_branch}},
        "close_source_branch": False,
    }
    code, data = _bitbucket_request("POST", f"/repositories/{workspace}/{repo}/pullrequests", body=payload)
    if code not in (200, 201):
        return False, None
    return True, str(data.get("links", {}).get("html", {}).get("href", ""))


def _bitbucket_bootstrap_for_dispatch(epic_key: str, epic_summary: str, fields: dict[str, Any], dispatch_issue_key: str, role: str) -> tuple[bool, str | None, str | None]:
    if not _bitbucket_enabled():
        return False, None, None
    if role not in ("developer", "devops-iac"):
        return False, None, None
    workspace = os.getenv("BITBUCKET_WORKSPACE", "").strip()
    repo, _repo_url = _bitbucket_resolve_repo_for_epic(epic_key, epic_summary, fields)
    main_branch = os.getenv("BITBUCKET_MAIN_BRANCH", "main").strip() or "main"
    if not workspace or not repo:
        return False, None, None

    branch_name = _bitbucket_branch_name(dispatch_issue_key, role)
    ok, branch_url = _bitbucket_ensure_branch(workspace, repo, branch_name, main_branch)
    if not ok:
        fallback = (
            f"Bitbucket repository is ready: {_repo_url}\n"
            f"Could not create feature branch '{branch_name}' automatically yet.\n"
            f"Reason: repository likely has no initial commit on '{main_branch}'.\n"
            "Create one initial commit, then rerun orchestrator dispatch."
        )
        _jira_request("POST", f"/rest/api/3/issue/{dispatch_issue_key}/comment", body={"body": _adf_text_body(fallback)})
        return True, _repo_url, None

    pr_url = None
    if _env_bool("BITBUCKET_ENABLE_PR_AUTOMATION", False):
        pr_ok, maybe_pr = _bitbucket_create_pr(workspace, repo, branch_name, main_branch, epic_key, dispatch_issue_key, role)
        if pr_ok:
            pr_url = maybe_pr

    guidance = (
        f"Bitbucket branch ready: {branch_name}\n"
        f"Branch URL: {branch_url}\n"
        f"Commit and PR must include keys {epic_key} and {dispatch_issue_key}."
    )
    if pr_url:
        guidance = f"{guidance}\nPR URL: {pr_url}"
    _jira_request("POST", f"/rest/api/3/issue/{dispatch_issue_key}/comment", body={"body": _adf_text_body(guidance)})
    return True, branch_url, pr_url


def _contains_any(text: str, words: list[str]) -> bool:
    n = _norm(text)
    return any(w in n for w in words)


def _label_safe(text: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", _norm(text)).strip("-")


def _adf_text_body(text: str) -> dict[str, Any]:
    return {
        "type": "doc",
        "version": 1,
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


def _dispatch_stage(current_status: str, proposed_next: str, gates_pass: bool) -> str:
    if gates_pass and proposed_next != current_status:
        return proposed_next
    return current_status


def _planned_dispatches(current_status: str, proposed_next: str, gates_pass: bool) -> list[dict[str, str]]:
    stage = _dispatch_stage(current_status, proposed_next, gates_pass)
    tasks = DISPATCH_TASKS_BY_STAGE.get(stage, [])
    return [{"agent_role": role, "task": task, "stage": stage} for role, task in tasks]


def _find_open_dispatch_issue(project_key: str, epic_key: str, role: str) -> str | None:
    epic_label = f"epic-{_label_safe(epic_key)}"
    role_label = f"agent-{_label_safe(role)}"
    jql = (
        f'project = "{project_key}" '
        f'AND labels = "orchestrator-dispatch" '
        f'AND labels = "{epic_label}" '
        f'AND labels = "{role_label}" '
        f"AND statusCategory != Done ORDER BY created DESC"
    )
    code, payload = _jira_request("GET", "/rest/api/3/search/jql", query={"jql": jql, "maxResults": "1", "fields": "key"})
    if code != 200:
        return None
    issues = payload.get("issues", [])
    if not issues:
        return None
    return str(issues[0].get("key", "")) or None


def _find_latest_dispatch_issue_for_stage(project_key: str, epic_key: str, role: str, stage: str) -> tuple[str | None, bool]:
    epic_label = f"epic-{_label_safe(epic_key)}"
    role_label = f"agent-{_label_safe(role)}"
    stage_label = f"stage-{_label_safe(stage)}"
    jql = (
        f'project = "{project_key}" '
        f'AND labels = "orchestrator-dispatch" '
        f'AND labels = "{epic_label}" '
        f'AND labels = "{role_label}" '
        f'AND labels = "{stage_label}" '
        f"ORDER BY created DESC"
    )
    code, payload = _jira_request("GET", "/rest/api/3/search/jql", query={"jql": jql, "maxResults": "1", "fields": "key,status"})
    if code != 200:
        return None, False
    issues = payload.get("issues", [])
    if not issues:
        return None, False
    key = str(issues[0].get("key", "")) or None
    status_cat = str(issues[0].get("fields", {}).get("status", {}).get("statusCategory", {}).get("name", ""))
    is_done = status_cat.lower() == "done"
    return key, is_done


def _find_stage_dispatch_issues(project_key: str, epic_key: str, stage: str) -> list[dict[str, Any]]:
    epic_label = f"epic-{_label_safe(epic_key)}"
    stage_label = f"stage-{_label_safe(stage)}"
    jql = (
        f'project = "{project_key}" '
        f'AND labels = "orchestrator-dispatch" '
        f'AND labels = "{epic_label}" '
        f'AND labels = "{stage_label}" '
        f"ORDER BY created DESC"
    )
    code, payload = _jira_request(
        "GET",
        "/rest/api/3/search/jql",
        query={"jql": jql, "maxResults": "100", "fields": "key,status,labels,summary"},
    )
    if code != 200:
        return []
    issues = payload.get("issues", [])
    return issues if isinstance(issues, list) else []


def _stage_dispatch_signoff_complete(project_key: str, epic_key: str, stage: str) -> tuple[bool, str]:
    tasks = DISPATCH_TASKS_BY_STAGE.get(stage, [])
    if not tasks:
        return True, ""

    required_roles = [role for role, _ in tasks]
    issues = _find_stage_dispatch_issues(project_key, epic_key, stage)

    role_to_latest: dict[str, dict[str, Any]] = {}
    for issue in issues:
        labels = issue.get("fields", {}).get("labels", [])
        labels = [str(x) for x in labels] if isinstance(labels, list) else []
        for role in required_roles:
            role_label = f"agent-{_label_safe(role)}"
            if role_label in labels and role not in role_to_latest:
                role_to_latest[role] = issue
                break

    missing_roles: list[str] = []
    open_issue_keys: list[str] = []
    for role in required_roles:
        issue = role_to_latest.get(role)
        if not issue:
            missing_roles.append(role)
            continue
        status_cat = str(issue.get("fields", {}).get("status", {}).get("statusCategory", {}).get("name", "")).lower()
        if status_cat != "done":
            open_issue_keys.append(str(issue.get("key", "")))

    if not missing_roles and not open_issue_keys:
        return True, ""

    notes_parts = []
    if missing_roles:
        notes_parts.append("missing_roles=" + ",".join(missing_roles))
    if open_issue_keys:
        notes_parts.append("open_issues=" + ",".join(open_issue_keys))
    return False, "; ".join(notes_parts)


def _find_open_dispatch_issues_for_epic(project_key: str, epic_key: str) -> list[str]:
    epic_label = f"epic-{_label_safe(epic_key)}"
    jql = (
        f'project = "{project_key}" '
        f'AND labels = "orchestrator-dispatch" '
        f'AND labels = "{epic_label}" '
        f"AND statusCategory != Done ORDER BY created DESC"
    )
    code, payload = _jira_request(
        "GET",
        "/rest/api/3/search/jql",
        query={"jql": jql, "maxResults": "100", "fields": "key"},
    )
    if code != 200:
        return []
    issues = payload.get("issues", [])
    if not isinstance(issues, list):
        return []
    return [str(i.get("key", "")) for i in issues if str(i.get("key", ""))]


def _link_issue_to_epic(epic_key: str, issue_key: str) -> bool:
    body = {
        "type": {"name": "Relates"},
        "inwardIssue": {"key": issue_key},
        "outwardIssue": {"key": epic_key},
    }
    code, _ = _jira_request("POST", "/rest/api/3/issueLink", body=body)
    return code in (200, 201)


def _create_dispatch_issue(project_key: str, epic_key: str, epic_summary: str, epic_fields: dict[str, Any], role: str, task: str, stage: str) -> tuple[bool, str | None, str | None]:
    # Do not create multiple stories for the same role within the same stage.
    stage_existing, stage_done = _find_latest_dispatch_issue_for_stage(project_key, epic_key, role, stage)
    if stage_existing:
        if stage_done:
            return False, stage_existing, None
        return False, stage_existing, None

    existing = _find_open_dispatch_issue(project_key, epic_key, role)
    if existing:
        _jira_request(
            "POST",
            f"/rest/api/3/issue/{existing}/comment",
            body={
                "body": _adf_text_body(
                    "\n".join(
                        [
                            "Orchestrator update:",
                            f"- Epic moved to stage: {stage}",
                            f"- Continue this story until sign-off: {task}",
                            "- Owner: AI agent for this role (no human assignee required).",
                            "- Keep all evidence and status updates in this same story.",
                        ]
                    )
                )
            },
        )
        return False, existing, None

    issue_type = os.getenv("ORCHESTRATOR_DISPATCH_ISSUE_TYPE", "Story").strip() or "Story"
    summary = f"[{epic_key}] [{role}] {task}"
    if len(summary) > 254:
        summary = summary[:251] + "..."

    labels = [
        "orchestrator-dispatch",
        f"epic-{_label_safe(epic_key)}",
        f"agent-{_label_safe(role)}",
        f"stage-{_label_safe(stage)}",
    ]
    req_values, req_missing = _required_items_snapshot({"fields": epic_fields})
    req_lines = []
    for key in REQUIRED_ITEM_ORDER:
        if key in req_values:
            req_lines.append(f"- {_required_item_label(key)}: {req_values[key][:700]}")
    missing_line = ", ".join(_required_item_label(item_id) for item_id in req_missing) if req_missing else "None"
    description = (
        f"Epic: {epic_key} - {epic_summary}\n"
        f"Stage: {stage}\n"
        f"Assigned agent role: {role}\n"
        "Execution model: AI agent executes this role. The only human participant is the Epic creator/customer.\n"
        f"Task: {task}\n\n"
        "Requirements snapshot from Epic:\n"
        f"{chr(10).join(req_lines) if req_lines else '- (no structured values found)'}\n\n"
        f"Missing required items: {missing_line}\n\n"
        "Definition of done for this story:\n"
        "- Update Epic with evidence links and outcome\n"
        "- Keep customer communication in Epic thread\n"
        "- Include Epic key in all related artifacts/PRs\n\n"
        "Created automatically by orchestrator."
    )
    payload = {
        "fields": {
            "project": {"key": project_key},
            "issuetype": {"name": issue_type},
            "summary": summary,
            "description": _adf_text_body(description),
            "labels": labels,
        }
    }
    code, data = _jira_request("POST", "/rest/api/3/issue", body=payload)
    if code not in (200, 201):
        return False, None, str(data.get("error", data))
    created_key = str(data.get("key", ""))
    if not created_key:
        return False, None, "missing_created_key"

    _link_issue_to_epic(epic_key, created_key)

    # Kickoff comment so the assignee sees explicit asks in activity stream.
    kickoff_lines = [
        f"Orchestrator dispatch kickoff for {role}.",
        f"Epic: {epic_key}",
        "Owner model: This work is executed by AI agents. Customer is the only human participant.",
        f"Task: {task}",
        "",
        "Definition of done:",
        "- Update Epic with concrete evidence links and outcomes",
        "- Keep customer communication in Epic thread",
        "- Include Epic key in related artifacts/PRs",
    ]
    if role == "po-requirements":
        missing_lines = [f"- {_required_item_label(item_id)}: {_required_item_question(item_id)}" for item_id in req_missing]
        kickoff_lines.extend(
            [
                "",
                "Please make sure the Epic clearly covers these required sections:",
                *(missing_lines if missing_lines else ["- All required sections are present. Keep them measurable and explicit."]),
            ]
        )
    _jira_request("POST", f"/rest/api/3/issue/{created_key}/comment", body={"body": _adf_text_body("\n".join(kickoff_lines))})
    return True, created_key, None


def _gate_checks_for_epic(epic: dict[str, Any]) -> list[dict[str, Any]]:
    fields = epic.get("fields", {})
    labels = fields.get("labels", [])
    labels = [str(x) for x in labels] if isinstance(labels, list) else []
    current_status, _ = _resolve_orchestrator_state(labels, str(fields.get("status", {}).get("name", "")))
    transition = STATE_TRANSITIONS.get(current_status)
    if not transition:
        return []
    _, gates = transition
    desc = _extract_description_text(fields.get("description"))
    comments = fields.get("comment", {}).get("comments", [])
    filtered_comments_texts: list[str] = []
    if isinstance(comments, list):
        for c in comments:
            text = _extract_text(c.get("body", {}))
            n = _norm(text)
            if "[orc-hash:" in n or n.startswith("orchestrator gate check:") or n.startswith("orchestrator update:"):
                continue
            filtered_comments_texts.append(text)
    comments_text = "\n".join(filtered_comments_texts)
    combined = f"{desc}\n{comments_text}"
    req_values, req_missing = _required_items_snapshot(epic)
    checks = []
    for gate in gates:
        passed = False
        notes = ""
        if gate == "initial_problem_goals_constraints":
            passed = len(desc.strip()) > 80
        elif gate == "confluence_templates_linked":
            markers = ["atlassian.net/wiki", "atlassian.net/spaces", "/spaces/", "confluence"]
            n = _norm(combined)
            seen = [m for m in markers if m in n]
            passed = bool(seen)
            notes = f"seen_markers={','.join(seen)}"
        elif gate == "customer_contact_confirmed":
            passed = fields.get("creator") is not None
        elif gate == "risk_level_set":
            passed = _contains_any(combined, ["risk level", "low", "medium", "high"])
        elif gate == "open_questions_initialized":
            passed = _contains_any(combined, ["open questions"])
        elif gate == "dor_required_items_complete":
            passed = len(req_missing) == 0
            if req_missing:
                notes = "Missing sections: " + ", ".join(_required_item_label(item_id) for item_id in req_missing)
        elif gate == "refinement_started":
            passed = _contains_any(combined, ["refinement", "kickoff", "started"])
        elif gate in ("stories_linked", "tasks_subtasks_linked"):
            passed = bool(fields.get("issuelinks"))
        elif gate == "ac_measurable":
            passed = _contains_any(combined, ["acceptance criteria", "given", "when", "then"])
        elif gate == "nfrs_filled_or_na":
            passed = _contains_any(combined, ["non-functional", "nfr", "n/a"])
        elif gate == "questions_resolved_or_tracked":
            passed = _contains_any(combined, ["customer answers", "assumptions", "decisions"])
        elif gate == "design_v1_linked":
            passed = _contains_any(combined, ["solution design", "design v1", "confluence", "architect documentation", "/wiki/spaces/"])
        elif gate == "adrs_linked":
            passed = _contains_any(combined, ["adr"])
        elif gate == "security_review_recorded":
            passed = _contains_any(combined, ["security review", "sign-off", "changes requested"])
        elif gate in ("ci_tests_pass", "sast_pass", "dependency_scan_pass", "secrets_scan_pass", "iac_scan_pass", "qa_evidence_linked"):
            passed = _contains_any(combined, [gate.replace("_", " "), "pipeline", "scan", "qa"])
        elif gate == "security_signoff_if_medium_high":
            passed = _contains_any(combined, ["security sign-off", "risk level: low"])
        elif gate in ("release_readiness_confirmed", "rollout_rollback_plan_exists", "release_notes_published", "runbook_updated", "deployment_evidence_linked"):
            passed = _contains_any(combined, ["release", "rollout", "rollback", "runbook", "deployment"])
        elif gate in ("delivery_run_started", "team_assigned"):
            passed = _contains_any(combined, ["run-id", "delivery metadata", "assigned"])
        checks.append({"gate": gate, "gate_label": _gate_label(gate), "passed": passed, "evidence_links": [], "notes": notes})
    return checks


def _build_orchestrator_missing_evidence_comment(current_status: str, proposed_next: str, gate_checks: list[dict[str, Any]]) -> str:
    missing = [str(g.get("gate", "")) for g in gate_checks if not bool(g.get("passed", False))]
    lines = [
        "Orchestrator gate check: evidence missing for transition.",
        f"Current state: {current_status}",
        f"Target state: {proposed_next}",
        "",
        "What is still missing:",
    ]
    for gate in missing:
        lines.append(f"- {_gate_label(gate)}")
    missing_required = [str(g.get("notes", "")) for g in gate_checks if str(g.get("gate", "")) == "dor_required_items_complete" and not bool(g.get("passed", False)) and str(g.get("notes", ""))]
    if missing_required:
        lines.extend(["", "Requirement details:", *[f"- {n}" for n in missing_required]])
    lines.extend(
        [
            "",
            "Please update the Epic with this information and links. I will re-check automatically.",
        ]
    )
    return "\n".join(lines)


def _orchestrator_missing_hash(current_status: str, proposed_next: str, gate_checks: list[dict[str, Any]]) -> str:
    missing_parts = []
    for g in gate_checks:
        if bool(g.get("passed", False)):
            continue
        gate_id = str(g.get("gate", ""))
        notes = str(g.get("notes", "")).strip()
        missing_parts.append(f"{gate_id}:{notes}")
    seed = f"{current_status}|{proposed_next}|{'|'.join(missing_parts)}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _has_orchestrator_hash(comments_block: Any, marker_hash: str) -> bool:
    if not marker_hash:
        return False
    text = _extract_text(comments_block)
    return f"[orc-hash:{marker_hash}]" in text


def _find_transition_id(issue_key: str, to_status: str) -> str | None:
    code, payload = _jira_request("GET", f"/rest/api/3/issue/{issue_key}/transitions")
    if code != 200:
        return None
    target = str(to_status or "").strip().upper()
    target_names = {target}
    target_names.update(str(v).strip().upper() for v in _status_aliases().get(target, []))
    for tr in payload.get("transitions", []):
        to_name = str(tr.get("to", {}).get("name", ""))
        if to_name.strip().upper() in target_names:
            return str(tr.get("id"))
    return None


def _transition_issue(issue_key: str, to_status: str) -> bool:
    transition_id = _find_transition_id(issue_key, to_status)
    if not transition_id:
        return False
    code, _ = _jira_request("POST", f"/rest/api/3/issue/{issue_key}/transitions", body={"transition": {"id": transition_id}})
    return code in (200, 204)


@app.route(route="review_epic", methods=["POST"])
def review_epic(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse("Invalid JSON body", status_code=400)
    epic = body.get("epic")
    comments = body.get("comments", [])
    cooldown_hours = int(body.get("cooldown_hours", os.getenv("AGENT_COMMENT_COOLDOWN_HOURS", "48")))
    if not isinstance(epic, dict):
        return func.HttpResponse("Missing or invalid 'epic' object", status_code=400)
    if not isinstance(comments, list):
        comments = []
    missing, evidence = _evaluate_missing_items(epic)
    if not missing:
        response = {
            "readiness": "ready",
            "question_hash": "ready",
            "comment_body": "Epic Readiness Review: Ready for Delivery.",
            "add_labels": ["ready-for-delivery"],
            "remove_labels": ["needs-info"],
            "evidence": evidence,
            "should_comment": False,
        }
    else:
        should_comment, cooldown_until, customer_responded = _cooldown_decision(comments, cooldown_hours)
        missing_ids = [item[0] for item in missing]
        response = {
            "readiness": "needs_info",
            "question_hash": hashlib.sha256("|".join(missing_ids).encode("utf-8")).hexdigest()[:16],
            "comment_body": _build_comment(missing),
            "template_comment_body": _build_template_comment(),
            "should_share_template": _should_share_template(epic, len(missing_ids)),
            "add_labels": ["needs-info"],
            "remove_labels": ["ready-for-delivery"],
            "missing_item_ids": missing_ids,
            "should_comment": should_comment,
            "cooldown_until": cooldown_until,
            "customer_responded_after_agent": customer_responded,
        }
    return func.HttpResponse(body=json.dumps(response), status_code=200, mimetype="application/json")


@app.route(route="execute_orchestrator_cycle", methods=["POST"])
def execute_orchestrator_cycle(req: func.HttpRequest) -> func.HttpResponse:
    try:
        payload = req.get_json()
    except ValueError:
        return func.HttpResponse(json.dumps({"error": "Invalid JSON body"}), status_code=400, mimetype="application/json")
    project_key = str(payload.get("project_key", "")).strip()
    mode = str(payload.get("mode", "")).strip()
    epic_key = str(payload.get("epic_key", "")).strip()
    dry_run = _to_bool(payload.get("dry_run", True), True)
    allow_transition = _to_bool(payload.get("allow_transition_execution", False), False)
    allow_dispatch = _to_bool(payload.get("allow_dispatch_execution", False), False)
    allow_comment = _to_bool(payload.get("allow_comment_execution", False), False)
    batch_limit = int(str(payload.get("batch_limit", 10)).strip() or "10")
    if not project_key or mode not in ("single_epic", "batch"):
        return func.HttpResponse(json.dumps({"error": "project_key and valid mode are required"}), status_code=400, mimetype="application/json")

    issues: list[dict[str, Any]] = []
    if mode == "single_epic":
        if not epic_key:
            return func.HttpResponse(json.dumps({"error": "epic_key required for single_epic mode"}), status_code=400, mimetype="application/json")
        code, data = _jira_request("GET", f"/rest/api/3/issue/{epic_key}", query={"fields": "summary,description,status,labels,creator,comment,issuelinks"})
        if code != 200:
            return func.HttpResponse(json.dumps({"error": "Failed to read epic", "details": data}), status_code=500, mimetype="application/json")
        issues = [data]
    else:
        jql = f'project = {project_key} AND issuetype = Epic AND status NOT IN ("DONE") ORDER BY created ASC'
        code, data = _jira_request("GET", "/rest/api/3/search/jql", query={"jql": jql, "maxResults": str(batch_limit), "fields": "summary,description,status,labels,creator,comment,issuelinks"})
        if code != 200:
            return func.HttpResponse(json.dumps({"error": "Failed to search epics", "details": data}), status_code=500, mimetype="application/json")
        issues = data.get("issues", [])

    out_items = []
    transitions_executed = 0
    dispatches_executed = 0
    comments_executed = 0
    for issue in issues:
        key = str(issue.get("key", ""))
        fields = issue.get("fields", {})
        labels = fields.get("labels", [])
        labels = [str(x) for x in labels] if isinstance(labels, list) else []
        jira_status = str(fields.get("status", {}).get("name", ""))
        current_status, state_source = _resolve_orchestrator_state(labels, jira_status)
        if not dry_run and allow_transition and current_status:
            if _sync_state_label(key, labels, current_status):
                if state_source != "label_and_jira":
                    executed_sync_marker = f"state_synced_from_{state_source}"
                else:
                    executed_sync_marker = ""
            else:
                executed_sync_marker = "state_sync_failed"
        else:
            executed_sync_marker = ""
        next_info = STATE_TRANSITIONS.get(current_status)
        proposed_next = next_info[0] if next_info else current_status
        gate_checks = _gate_checks_for_epic(issue)
        if DISPATCH_TASKS_BY_STAGE.get(current_status):
            stage_signoff_ok, stage_signoff_notes = _stage_dispatch_signoff_complete(project_key, key, current_status)
            gate_checks.append(
                {
                    "gate": "stage_dispatch_signoff_complete",
                    "gate_label": _gate_label("stage_dispatch_signoff_complete"),
                    "passed": stage_signoff_ok,
                    "evidence_links": [],
                    "notes": stage_signoff_notes,
                }
            )
        if proposed_next == "DONE":
            open_dispatch = _find_open_dispatch_issues_for_epic(project_key, key)
            gate_checks.append(
                {
                    "gate": "all_dispatch_stories_done",
                    "gate_label": _gate_label("all_dispatch_stories_done"),
                    "passed": len(open_dispatch) == 0,
                    "evidence_links": [],
                    "notes": ("" if not open_dispatch else "open_issues=" + ",".join(open_dispatch)),
                }
            )
        gates_pass = all(g.get("passed", False) for g in gate_checks) if gate_checks else False
        proposed_actions = []
        executed_actions = []
        errors = []
        customer_decision_required = False
        dispatches = _planned_dispatches(current_status, proposed_next, gates_pass)
        if executed_sync_marker:
            executed_actions.append(executed_sync_marker)

        if not gates_pass and gate_checks:
            proposed_actions.append("collect_missing_evidence")
        if gates_pass and next_info and proposed_next != current_status:
            proposed_actions.append(f"transition_{current_status}_to_{proposed_next}")
            if not dry_run and allow_transition:
                if _transition_issue(key, proposed_next):
                    _sync_state_label(key, labels, proposed_next)
                    transitions_executed += 1
                    executed_actions.append(f"transitioned_to_{proposed_next}")
                else:
                    errors.append("transition_failed")
        if dispatches:
            proposed_actions.append("dispatch_agent_tasks")
        role_issue_keys: dict[str, str] = {}
        role_dispatch_meta: dict[str, dict[str, str | None]] = {}
        for dispatch in dispatches:
            dispatch["executed"] = False
            dispatch["issue_key"] = None
            dispatch["bitbucket_branch_url"] = None
            dispatch["bitbucket_pr_url"] = None
            if not dry_run and allow_dispatch:
                created, issue_key, err = _create_dispatch_issue(
                    project_key=project_key,
                    epic_key=key,
                    epic_summary=str(fields.get("summary", "")),
                    epic_fields=fields,
                    role=dispatch["agent_role"],
                    task=dispatch["task"],
                    stage=dispatch["stage"],
                )
                if issue_key:
                    dispatch["issue_key"] = issue_key
                    role_issue_keys[dispatch["agent_role"]] = issue_key
                    role_dispatch_meta[dispatch["agent_role"]] = {
                        "issue_key": issue_key,
                        "branch_url": None,
                        "pr_url": None,
                    }
                if created:
                    dispatch["executed"] = True
                    dispatches_executed += 1
                    bb_ok, bb_url, pr_url = _bitbucket_bootstrap_for_dispatch(
                        key,
                        str(fields.get("summary", "")),
                        fields,
                        issue_key,
                        dispatch["agent_role"],
                    )
                    if bb_ok:
                        dispatch["bitbucket_branch_url"] = bb_url
                        dispatch["bitbucket_pr_url"] = pr_url
                        role_dispatch_meta.setdefault(dispatch["agent_role"], {}).update(
                            {"branch_url": bb_url, "pr_url": pr_url}
                        )
                        executed_actions.append(f"bitbucket_branch_created:{issue_key}")
                        if pr_url:
                            executed_actions.append(f"bitbucket_pr_created:{issue_key}")
                elif err:
                    errors.append(f"dispatch_failed:{dispatch['agent_role']}")

        # Actual execution for architect+security in IN REFINEMENT:
        # create Confluence docs, perform cross-review/sign-off, and close both stories.
        effective_stage = _dispatch_stage(current_status, proposed_next, gates_pass)
        if not dry_run and allow_dispatch and effective_stage == "IN REFINEMENT":
            arch_key = role_issue_keys.get("architect")
            sec_key = role_issue_keys.get("security-architect")
            if arch_key and sec_key:
                ok, reason = _auto_execute_architect_security(
                    key,
                    str(fields.get("summary", "")),
                    arch_key,
                    sec_key,
                )
                if ok:
                    executed_actions.append("architect_security_auto_executed")
                else:
                    errors.append(f"architect_security_auto_failed:{reason}")

        if not dry_run and allow_dispatch and effective_stage == "READY FOR DELIVERY":
            devops_key = role_issue_keys.get("devops-iac")
            if devops_key:
                meta = role_dispatch_meta.get("devops-iac", {})
                ok, reason = _auto_execute_devops_iac(
                    key,
                    str(fields.get("summary", "")),
                    devops_key,
                    str(meta.get("branch_url") or "") or None,
                    str(meta.get("pr_url") or "") or None,
                )
                if ok:
                    executed_actions.append("devops_iac_auto_executed")
                else:
                    errors.append(f"devops_iac_auto_failed:{reason}")
            developer_key = role_issue_keys.get("developer")
            if developer_key:
                meta = role_dispatch_meta.get("developer", {})
                ok, reason = _auto_execute_developer(
                    key,
                    str(fields.get("summary", "")),
                    developer_key,
                    str(meta.get("branch_url") or "") or None,
                    str(meta.get("pr_url") or "") or None,
                )
                if ok:
                    executed_actions.append("developer_auto_executed")
                else:
                    errors.append(f"developer_auto_failed:{reason}")
            tester_key = role_issue_keys.get("tester-qa")
            if tester_key:
                ok, reason = _auto_execute_tester_qa(
                    key,
                    str(fields.get("summary", "")),
                    tester_key,
                )
                if ok:
                    executed_actions.append("tester_qa_auto_executed")
                else:
                    errors.append(f"tester_qa_auto_failed:{reason}")
            finops_key = role_issue_keys.get("finops")
            if finops_key:
                ok, reason = _auto_execute_finops(
                    key,
                    str(fields.get("summary", "")),
                    finops_key,
                )
                if ok:
                    executed_actions.append("finops_auto_executed")
                else:
                    errors.append(f"finops_auto_failed:{reason}")

        if not dry_run and allow_dispatch and effective_stage == "READY FOR RELEASE":
            release_key = role_issue_keys.get("release-manager")
            if release_key:
                ok, reason = _auto_execute_release_manager(
                    key,
                    str(fields.get("summary", "")),
                    release_key,
                )
                if ok:
                    executed_actions.append("release_manager_auto_executed")
                else:
                    errors.append(f"release_manager_auto_failed:{reason}")

        if not gates_pass and allow_comment and not dry_run:
            missing_hash = _orchestrator_missing_hash(current_status, proposed_next, gate_checks)
            if _has_orchestrator_hash(fields.get("comment", {}), missing_hash):
                out_items.append(
                    {
                        "epic_key": key,
                        "jira_status": jira_status,
                        "current_status": current_status,
                        "proposed_next_status": proposed_next,
                        "transition_executed": any(a.startswith("transitioned_to_") for a in executed_actions),
                        "gate_checks": gate_checks,
                        "approval_checks": [],
                        "dispatches": dispatches,
                        "customer_decision_required": customer_decision_required,
                        "proposed_actions": proposed_actions,
                        "executed_actions": executed_actions,
                        "errors": errors,
                    }
                )
                continue
            comment = _build_orchestrator_missing_evidence_comment(current_status, proposed_next, gate_checks)
            comment = f"{comment}\n\n[orc-hash:{missing_hash}]"
            code, _ = _jira_request("POST", f"/rest/api/3/issue/{key}/comment", body={"body": _adf_text_body(comment)})
            if code in (200, 201):
                comments_executed += 1
                executed_actions.append("comment_posted")

        out_items.append(
            {
                "epic_key": key,
                "jira_status": jira_status,
                "current_status": current_status,
                "proposed_next_status": proposed_next,
                "transition_executed": any(a.startswith("transitioned_to_") for a in executed_actions),
                "gate_checks": gate_checks,
                "approval_checks": [],
                "dispatches": dispatches,
                "customer_decision_required": customer_decision_required,
                "proposed_actions": proposed_actions,
                "executed_actions": executed_actions,
                "errors": errors,
            }
        )

    response = {
        "run_id": f"orchestrator-{datetime.now(timezone.utc).isoformat()}",
        "mode": mode,
        "summary": {
            "epics_evaluated": len(out_items),
            "transitions_executed": transitions_executed,
            "dispatches_executed": dispatches_executed,
            "comments_executed": comments_executed,
            "blocked_items": 0,
        },
        "items": out_items,
    }
    return func.HttpResponse(body=json.dumps(response), status_code=200, mimetype="application/json")


@app.route(route="openapi.execute_orchestrator_cycle.v1.json", methods=["GET"])
def openapi_execute_orchestrator_cycle(req: func.HttpRequest) -> func.HttpResponse:
    host = req.url.split("/api/")[0]
    spec = {
        "openapi": "3.0.3",
        "info": {"title": "Orchestrator Runbook Tool API", "version": "1.0.0"},
        "servers": [{"url": host}],
        "paths": {
            "/api/execute_orchestrator_cycle": {
                "post": {
                    "operationId": "execute_orchestrator_cycle",
                    "security": [{"ApiKeyAuth": []}],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"type": "object", "required": ["project_key", "mode"]}}},
                    },
                    "responses": {"200": {"description": "Cycle evaluation result"}},
                }
            }
        },
        "components": {"securitySchemes": {"ApiKeyAuth": {"type": "apiKey", "in": "query", "name": "code"}}},
    }
    return func.HttpResponse(body=json.dumps(spec), status_code=200, mimetype="application/json")
