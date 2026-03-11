"""
Post delivery evidence comment to a Jira epic via the tool adapter.
Usage: python scripts/post_delivery_comment.py --epic KAN-148 --pr-url <url> [--repo-slug <slug>]
"""

import argparse
import os
import sys
import json
import requests
from datetime import datetime

# ── Load .env ──────────────────────────────────────────────────────────────────
env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

TOOL_BASE = os.environ.get("REVIEW_ENDPOINT_BASE_URL", "https://epicreview257529268.azurewebsites.net/api")
ADD_COMMENT_URL = f"{TOOL_BASE}/tool/jira/add_comment"


def post_comment(issue_key: str, comment: str) -> dict:
    resp = requests.post(
        ADD_COMMENT_URL,
        json={"issue_key": issue_key, "comment": comment},
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def build_comment(epic_key: str, pr_url: str, repo_slug: str) -> str:
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"*[Automated] Delivery Pack Ready — {ts}*",
        "",
        f"The delivery pack for *{epic_key}* has been prepared and a Pull Request is open for review.",
        "",
        f"*Bitbucket PR:* {pr_url}",
    ]
    if repo_slug:
        lines.append(f"*Repository:* https://bitbucket.org/shahosa/{repo_slug}")
    lines += [
        "",
        "*What's included:*",
        "- Dockerfile + .dockerignore",
        "- Bitbucket Pipelines CI/CD (`bitbucket-pipelines.yml`)",
        "- Azure Bicep infra (`infra/bicep/main.bicep`)",
        "- Deploy + e2e-local scripts",
        "- `PR_METADATA.md` with epic context",
        "",
        "*Next steps:*",
        "1. Review and approve the PR in Bitbucket",
        "2. Set required pipeline variables (see `docs/KAN-148_PR_CHECKLIST.md`)",
        "3. Merge → CI/CD pipeline auto-deploys to Azure Container Apps",
        "",
        "_Posted by Spec2Code delivery automation_",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Post delivery comment to Jira")
    parser.add_argument("--epic", required=True, help="Jira epic key, e.g. KAN-148")
    parser.add_argument("--pr-url", default="https://bitbucket.org/shahosa/kan148-shopping-list-app/pull-requests/1",
                        help="Bitbucket PR URL")
    parser.add_argument("--repo-slug", default="kan148-shopping-list-app", help="Bitbucket repo slug")
    args = parser.parse_args()

    comment = build_comment(args.epic, args.pr_url, args.repo_slug)
    print(f"Posting comment to {args.epic} via {ADD_COMMENT_URL} …")
    print("─" * 60)
    print(comment)
    print("─" * 60)

    try:
        result = post_comment(args.epic, comment)
        print(f"\ncomment_posted=True")
        print(f"epic={args.epic}")
        print(f"pr_url={args.pr_url}")
    except requests.HTTPError as e:
        body = ""
        try:
            body = e.response.text
        except Exception:
            pass
        print(f"\nERROR {e.response.status_code}: {body}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
