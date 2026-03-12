#!/usr/bin/env bash
set -euo pipefail

# Optional: set AZURE_CONFIG_DIR externally when running in restricted environments.
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

get_secret_from_kv() {
  local vault_name="$1"
  local secret_name="$2"
  az keyvault secret show \
    --vault-name "${vault_name}" \
    --name "${secret_name}" \
    --query value \
    -o tsv \
    --only-show-errors
}

PROJECT_ENDPOINT="${AI_FOUNDRY_PROJECT_ENDPOINT:-$(get_env AI_FOUNDRY_PROJECT_ENDPOINT)}"
PROJECT_NAME="${AI_FOUNDRY_PROJECT_NAME:-$(get_env AI_FOUNDRY_PROJECT_NAME)}"
AGENT_NAME="${AI_FOUNDRY_ORCHESTRATOR_AGENT_NAME:-$(get_env AI_FOUNDRY_ORCHESTRATOR_AGENT_NAME)}"
MODEL_DEPLOYMENT="${AI_FOUNDRY_MODEL_DEPLOYMENT:-$(get_env AI_FOUNDRY_MODEL_DEPLOYMENT)}"
API_VERSION="${AI_FOUNDRY_API_VERSION:-2025-05-15-preview}"

REVIEW_ENDPOINT_BASE_URL="${REVIEW_ENDPOINT_BASE_URL:-$(get_env REVIEW_ENDPOINT_BASE_URL)}"
REVIEW_ENDPOINT_API_KEY="${REVIEW_ENDPOINT_API_KEY:-$(get_env REVIEW_ENDPOINT_API_KEY)}"
AZURE_KEY_VAULT_NAME="${AZURE_KEY_VAULT_NAME:-$(get_env AZURE_KEY_VAULT_NAME)}"
REVIEW_ENDPOINT_API_KEY_SECRET_NAME="${REVIEW_ENDPOINT_API_KEY_SECRET_NAME:-$(get_env REVIEW_ENDPOINT_API_KEY_SECRET_NAME)}"
AI_FOUNDRY_OPENAPI_PROJECT_CONNECTION_ID="${AI_FOUNDRY_OPENAPI_PROJECT_CONNECTION_ID:-$(get_env AI_FOUNDRY_OPENAPI_PROJECT_CONNECTION_ID)}"

AGENT_NAME="${AGENT_NAME:-orchestrator-agent}"

if [[ -z "${PROJECT_ENDPOINT}" ]]; then
  if [[ -n "${PROJECT_NAME}" ]]; then
    echo "Missing AI_FOUNDRY_PROJECT_ENDPOINT."
    echo "Set it in .env like:"
    echo "AI_FOUNDRY_PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/${PROJECT_NAME}"
  else
    echo "Missing AI_FOUNDRY_PROJECT_ENDPOINT in .env."
  fi
  exit 1
fi

if [[ -z "${MODEL_DEPLOYMENT}" ]]; then
  MODEL_DEPLOYMENT="gpt-4o-mini"
fi

TOKEN="$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv --only-show-errors 2>/dev/null || true)"
if [[ -z "${TOKEN}" ]]; then
  echo "Azure login required. Run:"
  if [[ -n "${AZURE_CONFIG_DIR:-}" ]]; then
    echo "export AZURE_CONFIG_DIR=${AZURE_CONFIG_DIR}"
  fi
  echo "az login"
  exit 1
fi

if [[ -z "${REVIEW_ENDPOINT_API_KEY}" && -n "${AZURE_KEY_VAULT_NAME}" && -n "${REVIEW_ENDPOINT_API_KEY_SECRET_NAME}" ]]; then
  REVIEW_ENDPOINT_API_KEY="$(get_secret_from_kv "${AZURE_KEY_VAULT_NAME}" "${REVIEW_ENDPOINT_API_KEY_SECRET_NAME}")"
fi

if [[ -z "${REVIEW_ENDPOINT_BASE_URL}" ]]; then
  echo "Missing REVIEW_ENDPOINT_BASE_URL."
  exit 1
fi
if [[ -z "${AI_FOUNDRY_OPENAPI_PROJECT_CONNECTION_ID}" ]]; then
  echo "Missing AI_FOUNDRY_OPENAPI_PROJECT_CONNECTION_ID."
  exit 1
fi

TOOLS_SERVER_URL="${REVIEW_ENDPOINT_BASE_URL%/api}"
INSTRUCTIONS_FILE="agents/orchestrator-agent/system-instructions.md"
[[ -f "${INSTRUCTIONS_FILE}" ]] || { echo "Missing ${INSTRUCTIONS_FILE}"; exit 1; }

tmp_payload="$(mktemp /tmp/foundry-orchestrator-payload.XXXXXX.json)"
tmp_tools_spec="$(mktemp /tmp/foundry-tools-spec.XXXXXX.json)"
cleanup() {
  rm -f "${tmp_payload}" "${tmp_tools_spec}"
}
trap cleanup EXIT

jq -n \
  --arg server_url "${TOOLS_SERVER_URL}" \
  '{
    openapi: "3.0.3",
    info: { title: "Foundry Tool Adapter API", version: "2.0.0" },
    servers: [{ url: $server_url }],
    paths: {
      "/api/tool/jira/get_issue_context": {
        post: {
          operationId: "jira_get_issue_context",
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
            "200": { description: "Issue context result" }
          }
        }
      },
      "/api/tool/jira/add_comment": {
        post: {
          operationId: "jira_add_comment",
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
            "200": { description: "Comment result" }
          }
        }
      },
      "/api/tool/jira/transition_issue": {
        post: {
          operationId: "jira_transition_issue",
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
            "200": { description: "Transition result" }
          }
        }
      },
      "/api/tool/jira/list_open_dispatch_issues": {
        post: {
          operationId: "jira_list_open_dispatch_issues",
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
            "200": { description: "Open dispatch issues result" }
          }
        }
      },
      "/api/tool/jira/create_dispatch_story": {
        post: {
          operationId: "jira_create_dispatch_story",
          requestBody: {
            required: true,
            content: {
              "application/json": {
                schema: {
                  type: "object",
                  required: ["project_key", "epic_key", "role", "task"],
                  properties: {
                    project_key: { type: "string" },
                    epic_key: { type: "string" },
                    role: { type: "string" },
                    task: { type: "string" },
                    stage: { type: "string" }
                  }
                }
              }
            }
          },
          responses: {
            "200": { description: "Dispatch story result" }
          }
        }
      },
      "/api/tool/confluence/create_page": {
        post: {
          operationId: "confluence_create_page",
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
            "200": { description: "Confluence page result" }
          }
        }
      },
      "/api/tool/runtime/execute_script": {
        post: {
          operationId: "runtime_execute_script",
          requestBody: {
            required: true,
            content: {
              "application/json": {
                schema: {
                  type: "object",
                  required: ["action"],
                  properties: {
                    action: { type: "string" },
                    epic_key: { type: "string" }
                  }
                }
              }
            }
          },
          responses: {
            "200": { description: "Script execution result" }
          }
        }
      },
      "/api/tool/runtime/check_url": {
        post: {
          operationId: "runtime_check_url",
          requestBody: {
            required: true,
            content: {
              "application/json": {
                schema: {
                  type: "object",
                  required: ["url"],
                  properties: {
                    url: { type: "string" }
                  }
                }
              }
            }
          },
          responses: {
            "200": { description: "Runtime URL check result" }
          }
        }
      },
      "/api/tool/foundry/run_role_agent": {
        post: {
          operationId: "foundry_run_role_agent",
          requestBody: {
            required: true,
            content: {
              "application/json": {
                schema: {
                  type: "object",
                  required: ["role", "epic_key", "story_key"],
                  properties: {
                    role: { type: "string" },
                    epic_key: { type: "string" },
                    story_key: { type: "string" },
                    details: { type: "string" }
                  }
                }
              }
            }
          },
          responses: {
            "200": { description: "Role agent execution result" }
          }
        }
      }
    },
    components: {
      securitySchemes: {
        functionKeyHeader: {
          type: "apiKey",
          name: "x-functions-key",
          in: "header"
        }
      }
    },
    security: [{ functionKeyHeader: [] }]
  }' > "${tmp_tools_spec}"

jq -n \
  --arg name "${AGENT_NAME}" \
  --arg model "${MODEL_DEPLOYMENT}" \
  --rawfile instructions "${INSTRUCTIONS_FILE}" \
  --slurpfile tools_spec "${tmp_tools_spec}" \
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
          auth: {
            type: "connection",
            security_scheme: { connection_id: $project_connection_id }
          },
          spec: $tools_spec[0]
        }
      }
    ]
  }' > "${tmp_payload}"

echo "Registering/updating Foundry assistant '${AGENT_NAME}' with OpenAPI tools..."
assistants_json="$(curl -sS -H "Authorization: Bearer ${TOKEN}" "${PROJECT_ENDPOINT}/assistants?api-version=${API_VERSION}")"
existing_id="$(echo "${assistants_json}" | jq -r --arg name "${AGENT_NAME}" '.data[]? | select(.name==$name) | .id' | head -n1)"

resp_file="$(mktemp /tmp/foundry-orchestrator-response.XXXXXX.json)"
if [[ -n "${existing_id}" ]]; then
  http_code="$(
    curl -sS -o "${resp_file}" -w "%{http_code}" \
      -X POST \
      -H "Authorization: Bearer ${TOKEN}" \
      -H "Content-Type: application/json" \
      "${PROJECT_ENDPOINT}/assistants/${existing_id}?api-version=${API_VERSION}" \
      --data @"${tmp_payload}"
  )"
else
  http_code="$(
    curl -sS -o "${resp_file}" -w "%{http_code}" \
      -X POST \
      -H "Authorization: Bearer ${TOKEN}" \
      -H "Content-Type: application/json" \
      "${PROJECT_ENDPOINT}/assistants?api-version=${API_VERSION}" \
      --data @"${tmp_payload}"
  )"
fi

if [[ "${http_code}" != "200" && "${http_code}" != "201" ]]; then
  echo "Foundry API call failed (HTTP ${http_code}):"
  cat "${resp_file}"
  rm -f "${resp_file}"
  exit 1
fi

echo "Success (HTTP ${http_code})."
jq '{name, id, model, tools: .tools}' "${resp_file}" || true
rm -f "${resp_file}"
