#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${AZURE_CONFIG_DIR:-}" ]]; then
  mkdir -p "${AZURE_CONFIG_DIR}"
fi

if [[ ! -f ".env" ]]; then
  echo "Missing .env file. Copy .env.example to .env and fill values."
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required."
  exit 1
fi

get_env() {
  grep "^$1=" .env | cut -d= -f2- || true
}

set_env() {
  local key="$1"
  local val="$2"
  if grep -q "^${key}=" .env; then
    sed -i '' "s#^${key}=.*#${key}=${val}#" .env
  else
    printf "\n%s=%s\n" "${key}" "${val}" >> .env
  fi
}

PROJECT_ENDPOINT="${AI_FOUNDRY_PROJECT_ENDPOINT:-$(get_env AI_FOUNDRY_PROJECT_ENDPOINT)}"
MODEL_DEPLOYMENT="${AI_FOUNDRY_MODEL_DEPLOYMENT:-$(get_env AI_FOUNDRY_MODEL_DEPLOYMENT)}"
ROLE_MODEL_MAP_JSON="${AI_FOUNDRY_ROLE_MODEL_MAP_JSON:-$(get_env AI_FOUNDRY_ROLE_MODEL_MAP_JSON)}"
API_VERSION="${AI_FOUNDRY_API_VERSION:-$(get_env AI_FOUNDRY_API_VERSION)}"
REVIEW_ENDPOINT_BASE_URL="${REVIEW_ENDPOINT_BASE_URL:-$(get_env REVIEW_ENDPOINT_BASE_URL)}"
AI_FOUNDRY_OPENAPI_PROJECT_CONNECTION_ID="${AI_FOUNDRY_OPENAPI_PROJECT_CONNECTION_ID:-$(get_env AI_FOUNDRY_OPENAPI_PROJECT_CONNECTION_ID)}"
FORCE_RECREATE_ASSISTANTS="${FORCE_RECREATE_ASSISTANTS:-false}"
ASSISTANT_NAME_SUFFIX="${ASSISTANT_NAME_SUFFIX:--v2}"

MODEL_DEPLOYMENT="${MODEL_DEPLOYMENT:-gpt-4.1-mini}"
API_VERSION="${API_VERSION:-2025-05-15-preview}"

if [[ -z "${PROJECT_ENDPOINT}" ]]; then
  echo "Missing AI_FOUNDRY_PROJECT_ENDPOINT in .env"
  exit 1
fi

TOOLS_SERVER_URL="${REVIEW_ENDPOINT_BASE_URL%/api}"
if [[ -z "${TOOLS_SERVER_URL}" ]]; then
  echo "Missing REVIEW_ENDPOINT_BASE_URL in .env"
  exit 1
fi
if [[ -z "${AI_FOUNDRY_OPENAPI_PROJECT_CONNECTION_ID}" ]]; then
  echo "Missing AI_FOUNDRY_OPENAPI_PROJECT_CONNECTION_ID in .env"
  echo "Best-practice mode only: no anonymous tool auth and no key-in-URL registration path."
  exit 1
fi

TOKEN="$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv --only-show-errors 2>/dev/null || true)"
if [[ -z "${TOKEN}" ]]; then
  echo "Azure login required. Run: az login"
  exit 1
fi

ROLE_SPECS=(
  "coordinator|coordinator-assistant${ASSISTANT_NAME_SUFFIX}|agents/coordinator-agent/system-instructions.md"
  "po-requirements|po-requirements-assistant${ASSISTANT_NAME_SUFFIX}|agents/po-requirements-agent/system-instructions.md"
  "architect|architect-assistant${ASSISTANT_NAME_SUFFIX}|agents/architect-agent/system-instructions.md"
  "security-architect|security-architect-assistant${ASSISTANT_NAME_SUFFIX}|agents/security-architect-agent/system-instructions.md"
  "devops-iac|devops-iac-assistant${ASSISTANT_NAME_SUFFIX}|agents/devops-iac-agent/system-instructions.md"
  "developer|developer-assistant${ASSISTANT_NAME_SUFFIX}|agents/developer-agent/system-instructions.md"
  "tester-qa|tester-qa-assistant${ASSISTANT_NAME_SUFFIX}|agents/tester-qa-agent/system-instructions.md"
  "finops|finops-assistant${ASSISTANT_NAME_SUFFIX}|agents/finops-agent/system-instructions.md"
  "release-manager|release-manager-assistant${ASSISTANT_NAME_SUFFIX}|agents/release-manager-agent/system-instructions.md"
)

ASSISTANTS_JSON="$(curl -sS -H "Authorization: Bearer ${TOKEN}" "${PROJECT_ENDPOINT}/assistants?api-version=${API_VERSION}")"

ensure_assistant() {
  local role="$1"
  local name="$2"
  local instructions_file="$3"
  local model="$4"
  local allowed_paths_json
  allowed_paths_json="$(role_allowed_paths_json "${role}")"
  local existing_id
  existing_id="$(echo "${ASSISTANTS_JSON}" | jq -r --arg name "${name}" '.data[]? | select(.name==$name) | .id' | head -n1)"
  if [[ "${FORCE_RECREATE_ASSISTANTS}" == "true" ]]; then
    existing_id=""
  fi

  local payload_file
  payload_file="$(mktemp -t foundry-assistant-payload).json"
  if [[ -n "${TOOLS_SERVER_URL}" && -n "${AI_FOUNDRY_OPENAPI_PROJECT_CONNECTION_ID}" ]]; then
    local spec_file
    spec_file="$(mktemp -t foundry-tools-spec).json"
    jq -n \
      --arg server_url "${TOOLS_SERVER_URL}" \
      --argjson allowed_paths "${allowed_paths_json}" \
      '{
        openapi: "3.0.3",
        info: {
          title: "Foundry Tool Adapter API",
          version: "1.0.0",
          description: "Tool adapter for Jira/Confluence/Bitbucket side effects."
        },
        servers: [{ url: $server_url }],
        paths: (
          {
          "/api/tool/jira/get_issue_context": {
            post: {
              operationId: "jira_get_issue_context",
              description: "Read compact Jira issue context for an epic/story.",
              security: [{ functionKey: [] }],
              requestBody: {
                required: true,
                content: {
                  "application/json": {
                    schema: {
                      type: "object",
                      required: ["issue_key"],
                      properties: {
                        issue_key: { type: "string" },
                        include_comments: { type: "boolean" },
                        max_comments: { type: "integer" }
                      }
                    }
                  }
                }
              },
              responses: {
                "200": {
                  description: "Jira issue context",
                  content: {
                    "application/json": {
                      schema: { type: "object" }
                    }
                  }
                }
              }
            }
          }
          ,
          "/api/tool/jira/add_comment": {
            post: {
              operationId: "jira_add_comment",
              description: "Add comment to Jira issue.",
              security: [{ functionKey: [] }],
              requestBody: {
                required: true,
                content: {
                  "application/json": {
                    schema: {
                      type: "object",
                      required: ["issue_key", "comment"],
                      properties: {
                        issue_key: { type: "string" },
                        comment: { type: "string" }
                      }
                    }
                  }
                }
              },
              responses: {
                "200": {
                  description: "Comment add result",
                  content: {
                    "application/json": {
                      schema: { type: "object" }
                    }
                  }
                }
              }
            }
          },
          "/api/tool/jira/transition_issue": {
            post: {
              operationId: "jira_transition_issue",
              description: "Transition Jira issue to target status.",
              security: [{ functionKey: [] }],
              requestBody: {
                required: true,
                content: {
                  "application/json": {
                    schema: {
                      type: "object",
                      required: ["issue_key", "to_status"],
                      properties: {
                        issue_key: { type: "string" },
                        to_status: { type: "string" }
                      }
                    }
                  }
                }
              },
              responses: {
                "200": {
                  description: "Transition result",
                  content: {
                    "application/json": {
                      schema: { type: "object" }
                    }
                  }
                }
              }
            }
          },
          "/api/tool/jira/list_open_dispatch_issues": {
            post: {
              operationId: "jira_list_open_dispatch_issues",
              description: "List open dispatch issues for an epic.",
              security: [{ functionKey: [] }],
              requestBody: {
                required: true,
                content: {
                  "application/json": {
                    schema: {
                      type: "object",
                      required: ["project_key", "epic_key"],
                      properties: {
                        project_key: { type: "string" },
                        epic_key: { type: "string" }
                      }
                    }
                  }
                }
              },
              responses: {
                "200": {
                  description: "Open dispatch issues",
                  content: {
                    "application/json": {
                      schema: { type: "object" }
                    }
                  }
                }
              }
            }
          },
          "/api/tool/confluence/create_page": {
            post: {
              operationId: "confluence_create_page",
              description: "Create Confluence page in configured space.",
              security: [{ functionKey: [] }],
              requestBody: {
                required: true,
                content: {
                  "application/json": {
                    schema: {
                      type: "object",
                      required: ["title", "storage_html"],
                      properties: {
                        title: { type: "string" },
                        storage_html: { type: "string" }
                      }
                    }
                  }
                }
              },
              responses: {
                "200": {
                  description: "Confluence create page result",
                  content: {
                    "application/json": {
                      schema: { type: "object" }
                    }
                  }
                }
              }
            }
          }
          }
          | with_entries(select(.key as $k | ($allowed_paths | index($k))))
        ),
        components: {
          securitySchemes: {
            functionKey: {
              type: "apiKey",
              in: "header",
              name: "x-functions-key"
            }
          }
        }
      }' > "${spec_file}"
    jq -n \
      --arg name "${name}" \
      --arg model "${model}" \
      --rawfile instructions "${instructions_file}" \
      --slurpfile openapi_spec "${spec_file}" \
      --arg project_connection_id "${AI_FOUNDRY_OPENAPI_PROJECT_CONNECTION_ID}" \
      '{
        name: $name,
        model: $model,
        instructions: $instructions,
        tools: [
          {
            type: "openapi",
            openapi: {
              name: "foundry_tools_api",
              description: "Execute actions against Jira/Confluence/Bitbucket through the review endpoint",
              auth: {
                type: "connection",
                security_scheme: {
                  connection_id: $project_connection_id
                }
              },
              spec: $openapi_spec[0]
            }
          }
        ]
      }' > "${payload_file}"
    rm -f "${spec_file}"
  else
    echo "Error: tool registration requires TOOLS_SERVER_URL and AI_FOUNDRY_OPENAPI_PROJECT_CONNECTION_ID."
    rm -f "${payload_file}"
    exit 1
  fi

  local out_file
  out_file="$(mktemp -t foundry-assistant-out).json"
  local code
  if [[ -n "${existing_id}" ]]; then
    code="$(
      curl -sS -o "${out_file}" -w "%{http_code}" \
        -X POST \
        -H "Authorization: Bearer ${TOKEN}" \
        -H "Content-Type: application/json" \
        "${PROJECT_ENDPOINT}/assistants/${existing_id}?api-version=${API_VERSION}" \
        --data @"${payload_file}"
    )"
    if [[ "${code}" != "200" ]]; then
      echo "Warning: assistant update failed for ${name} (HTTP ${code}), keeping existing id ${existing_id}" >&2
      rm -f "${payload_file}" "${out_file}"
      echo "${existing_id}"
      return 0
    fi
    echo "$(jq -r '.id' "${out_file}")"
    rm -f "${payload_file}" "${out_file}"
    return 0
  fi

  code="$(
    curl -sS -o "${out_file}" -w "%{http_code}" \
      -X POST \
      -H "Authorization: Bearer ${TOKEN}" \
      -H "Content-Type: application/json" \
      "${PROJECT_ENDPOINT}/assistants?api-version=${API_VERSION}" \
      --data @"${payload_file}"
  )"
  if [[ "${code}" != "200" && "${code}" != "201" ]]; then
    echo "Failed creating assistant ${name} (HTTP ${code}):"
    cat "${out_file}"
    rm -f "${payload_file}" "${out_file}"
    exit 1
  fi
  echo "$(jq -r '.id' "${out_file}")"
  rm -f "${payload_file}" "${out_file}"
}

role_allowed_paths_json() {
  local role="$1"
  case "${role}" in
    coordinator)
      printf '%s\n' '["/api/tool/jira/get_issue_context","/api/tool/jira/add_comment","/api/tool/jira/transition_issue","/api/tool/jira/list_open_dispatch_issues","/api/tool/confluence/create_page"]'
      ;;
    po-requirements)
      printf '%s\n' '["/api/tool/jira/get_issue_context","/api/tool/jira/add_comment"]'
      ;;
    architect|security-architect|devops-iac|developer|tester-qa|finops|release-manager)
      printf '%s\n' '["/api/tool/jira/get_issue_context","/api/tool/jira/add_comment","/api/tool/confluence/create_page"]'
      ;;
    *)
      printf '%s\n' '["/api/tool/jira/get_issue_context","/api/tool/jira/add_comment"]'
      ;;
  esac
}

role_model_for() {
  local role="$1"
  if [[ -n "${ROLE_MODEL_MAP_JSON}" ]]; then
    local mapped
    mapped="$(printf '%s' "${ROLE_MODEL_MAP_JSON}" | jq -r --arg role "${role}" '.[$role] // empty' 2>/dev/null || true)"
    if [[ -n "${mapped}" && "${mapped}" != "null" ]]; then
      echo "${mapped}"
      return 0
    fi
  fi
  echo "${MODEL_DEPLOYMENT}"
}

ROLE_MAP="{}"
for spec in "${ROLE_SPECS[@]}"; do
  IFS='|' read -r role assistant_name instructions_file <<< "${spec}"
  if [[ ! -f "${instructions_file}" ]]; then
    echo "Missing ${instructions_file}"
    exit 1
  fi
  role_model="$(role_model_for "${role}")"
  echo "Ensuring assistant ${assistant_name} for role ${role} (model=${role_model})..."
  assistant_id="$(ensure_assistant "${role}" "${assistant_name}" "${instructions_file}" "${role_model}")"
  if [[ -z "${assistant_id}" || "${assistant_id}" == "null" ]]; then
    echo "Failed to resolve assistant id for ${role}"
    exit 1
  fi
  ROLE_MAP="$(echo "${ROLE_MAP}" | jq -c --arg role "${role}" --arg id "${assistant_id}" '. + {($role): $id}')"
done

set_env AI_FOUNDRY_API_VERSION "${API_VERSION}"
set_env AI_FOUNDRY_LOGGING_ENABLED "true"
set_env AI_FOUNDRY_ROLE_AGENT_MAP_JSON "${ROLE_MAP}"

echo "Updated .env:"
echo "AI_FOUNDRY_API_VERSION=${API_VERSION}"
echo "AI_FOUNDRY_LOGGING_ENABLED=true"
echo "AI_FOUNDRY_ROLE_AGENT_MAP_JSON=${ROLE_MAP}"
