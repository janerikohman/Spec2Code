#!/usr/bin/env python3
import argparse
import base64
import subprocess
from datetime import datetime
from pathlib import Path

import requests


def read_env(path: Path) -> dict:
    cfg = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        cfg[key.strip()] = value.strip()
    return cfg


def az_secret(vault: str, name: str) -> str:
    result = subprocess.run(
        [
            "az",
            "keyvault",
            "secret",
            "show",
            "--vault-name",
            vault,
            "--name",
            name,
            "--query",
            "value",
            "-o",
            "tsv",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def auth_headers(email: str, token: str) -> dict:
    basic = base64.b64encode(f"{email}:{token}".encode()).decode()
    return {
        "Authorization": f"Basic {basic}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def get_branch(workspace: str, repo: str, branch: str, headers: dict):
    url = f"https://api.bitbucket.org/2.0/repositories/{workspace}/{repo}/refs/branches/{branch}"
    r = requests.get(url, headers=headers, timeout=30)
    if r.status_code == 200:
        return r.json()
    if r.status_code == 404:
        return None
    raise RuntimeError(f"Branch lookup failed ({branch}): {r.status_code} {r.text[:200]}")


def ensure_destination_branch(workspace: str, repo: str, src_branch: str, dst_branch: str, headers: dict):
    dst = get_branch(workspace, repo, dst_branch, headers)
    if dst is not None:
        return dst_branch

    src = get_branch(workspace, repo, src_branch, headers)
    if src is None:
        raise RuntimeError(f"Source branch does not exist: {src_branch}")

    create_url = f"https://api.bitbucket.org/2.0/repositories/{workspace}/{repo}/refs/branches"
    payload = {"name": dst_branch, "target": {"hash": src["target"]["hash"]}}
    r = requests.post(create_url, headers=headers, json=payload, timeout=30)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Failed to create destination branch {dst_branch}: {r.status_code} {r.text[:300]}")
    return dst_branch


def existing_open_pr(workspace: str, repo: str, src_branch: str, dst_branch: str, headers: dict):
    url = (
        f"https://api.bitbucket.org/2.0/repositories/{workspace}/{repo}/pullrequests"
        f"?state=OPEN&pagelen=50"
    )
    r = requests.get(url, headers=headers, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Failed to query PRs: {r.status_code} {r.text[:200]}")
    for pr in r.json().get("values", []):
        src = ((pr.get("source") or {}).get("branch") or {}).get("name")
        dst = ((pr.get("destination") or {}).get("branch") or {}).get("name")
        if src == src_branch and dst == dst_branch:
            return pr
    return None


def create_pr(workspace: str, repo: str, src_branch: str, dst_branch: str, title: str, body: str, headers: dict):
    url = f"https://api.bitbucket.org/2.0/repositories/{workspace}/{repo}/pullrequests"
    payload = {
        "title": title,
        "description": body,
        "source": {"branch": {"name": src_branch}},
        "destination": {"branch": {"name": dst_branch}},
        "close_source_branch": False,
    }
    r = requests.post(url, headers=headers, json=payload, timeout=30)
    return r


def commit_pr_marker(workspace: str, repo: str, branch: str, email: str, token: str, epic: str):
    url = f"https://api.bitbucket.org/2.0/repositories/{workspace}/{repo}/src"
    marker = (
        f"# PR Metadata\n\n"
        f"Epic: {epic}\n"
        f"Branch: {branch}\n"
        f"Generated: {datetime.utcnow().isoformat()}Z\n"
    )
    data = {
        "branch": branch,
        "message": f"chore({epic}): add PR metadata marker",
    }
    files = {
        "PR_METADATA.md": ("PR_METADATA.md", marker.encode("utf-8")),
    }
    r = requests.post(url, auth=(email, token), data=data, files=files, timeout=30)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Failed to add PR marker commit: {r.status_code} {r.text[:300]}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epic", required=True)
    parser.add_argument("--repo-slug", default="kan148-shopping-list-app")
    parser.add_argument("--source-branch", default="")
    parser.add_argument("--dest-branch", default="main")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    cfg = read_env(root / ".env")

    workspace = cfg["BITBUCKET_WORKSPACE"]
    email = cfg["BITBUCKET_EMAIL"]
    vault = cfg["AZURE_KEY_VAULT_NAME"]
    token_secret = cfg.get("BITBUCKET_API_TOKEN_SECRET_NAME", "bitbucket-api-token")
    token = az_secret(vault, token_secret)

    source_branch = args.source_branch or f"epic/{args.epic.lower()}-delivery-pack"
    headers = auth_headers(email, token)

    destination_branch = ensure_destination_branch(
        workspace=workspace,
        repo=args.repo_slug,
        src_branch=source_branch,
        dst_branch=args.dest_branch,
        headers=headers,
    )

    title = f"KAN-148: Delivery pack bootstrap for shopping-list app"
    body = """## Summary
- Bootstrap repository with delivery pack for KAN-148
- Add CI/CD pipeline, Dockerfile, and Azure Bicep baseline
- Add local smoke-test script and infra deployment helper

## Included files
- `bitbucket-pipelines.yml`
- `Dockerfile`
- `.dockerignore`
- `infra/bicep/main.bicep`
- `infra/bicep/deploy.sh`
- `scripts/e2e-local.sh`
- `infra/README-delivery-pack.md`
- `EPIC_PREPARED.md`

## Pre-merge checklist
- [ ] Configure Bitbucket repository variables/secrets for Azure deploy
- [ ] Confirm pipeline runs successfully on this PR
- [ ] Validate `scripts/e2e-local.sh` passes for the app code
- [ ] Align app artifact/build command with pipeline steps
- [ ] Approve and merge

## Required pipeline variables
- `AZURE_CLIENT_ID`
- `AZURE_CLIENT_SECRET`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_RESOURCE_GROUP`
- `AZURE_LOCATION`
- `AZURE_WEBAPP_NAME`
- `AZURE_PLAN_NAME`
- `AZURE_PLAN_SKU` (optional)
"""

    existing = existing_open_pr(
        workspace=workspace,
        repo=args.repo_slug,
        src_branch=source_branch,
        dst_branch=destination_branch,
        headers=headers,
    )

    if existing:
        pr = existing
        created = False
    else:
        pr_resp = create_pr(
            workspace=workspace,
            repo=args.repo_slug,
            src_branch=source_branch,
            dst_branch=destination_branch,
            title=title,
            body=body,
            headers=headers,
        )

        if pr_resp.status_code in (200, 201):
            pr = pr_resp.json()
            created = True
        elif pr_resp.status_code == 400 and "no changes to be pulled" in pr_resp.text.lower():
            commit_pr_marker(
                workspace=workspace,
                repo=args.repo_slug,
                branch=source_branch,
                email=email,
                token=token,
                epic=args.epic,
            )
            pr_retry = create_pr(
                workspace=workspace,
                repo=args.repo_slug,
                src_branch=source_branch,
                dst_branch=destination_branch,
                title=title,
                body=body,
                headers=headers,
            )
            if pr_retry.status_code not in (200, 201):
                raise RuntimeError(f"PR creation failed after marker commit: {pr_retry.status_code} {pr_retry.text[:300]}")
            pr = pr_retry.json()
            created = True
        else:
            raise RuntimeError(f"PR creation failed: {pr_resp.status_code} {pr_resp.text[:300]}")

    print(f"pr_created={created}")
    print(f"pr_id={pr.get('id')}")
    print(f"pr_state={pr.get('state')}")
    print(f"source_branch={source_branch}")
    print(f"destination_branch={destination_branch}")
    print(f"pr_url={(pr.get('links') or {}).get('html', {}).get('href', '')}")


if __name__ == "__main__":
    main()
