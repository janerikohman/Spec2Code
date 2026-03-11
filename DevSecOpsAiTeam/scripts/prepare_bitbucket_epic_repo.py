#!/usr/bin/env python3
import argparse
import base64
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

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


def run(cmd, cwd=None, check=True, env=None):
    result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, env=env)
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
    return result


def get_kv_secret(vault: str, secret_name: str) -> str:
    result = run(
        [
            "az",
            "keyvault",
            "secret",
            "show",
            "--vault-name",
            vault,
            "--name",
            secret_name,
            "--query",
            "value",
            "-o",
            "tsv",
        ]
    )
    return result.stdout.strip()


def bitbucket_headers(email: str, token: str) -> dict:
    auth = base64.b64encode(f"{email}:{token}".encode()).decode()
    return {
        "Authorization": f"Basic {auth}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def ensure_repo(workspace: str, slug: str, project_key: str, headers: dict):
    repo_url = f"https://api.bitbucket.org/2.0/repositories/{workspace}/{slug}"
    read_resp = requests.get(repo_url, headers=headers, timeout=30)
    if read_resp.status_code == 200:
        return read_resp.json(), False
    if read_resp.status_code != 404:
        raise RuntimeError(f"Failed checking repository: {read_resp.status_code} {read_resp.text[:300]}")

    payload = {
        "scm": "git",
        "is_private": True,
        "description": "KAN-148 shopping-list epic delivery repository",
    }
    if project_key:
        payload["project"] = {"key": project_key}

    create_resp = requests.post(repo_url, headers=headers, json=payload, timeout=30)
    if create_resp.status_code not in (200, 201):
        raise RuntimeError(f"Failed creating repository: {create_resp.status_code} {create_resp.text[:300]}")

    return create_resp.json(), True


def branch_head(workspace: str, slug: str, branch: str, headers: dict):
    url = f"https://api.bitbucket.org/2.0/repositories/{workspace}/{slug}/refs/branches/{branch}"
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code == 200:
        return resp.json().get("target", {}).get("hash")
    if resp.status_code == 404:
        return None
    raise RuntimeError(f"Failed getting branch info: {resp.status_code} {resp.text[:300]}")


def commit_files_via_api(workspace: str, slug: str, branch: str, main_branch: str, email: str, token: str, epic: str):
    root = Path(__file__).resolve().parents[1]
    template = root / "templates" / "shopping-list-delivery-pack"

    files_to_commit = {
        "bitbucket-pipelines.yml": template / "bitbucket-pipelines.yml",
        "Dockerfile": template / "Dockerfile",
        ".dockerignore": template / ".dockerignore",
        "infra/bicep/main.bicep": template / "infra" / "bicep" / "main.bicep",
        "infra/bicep/deploy.sh": template / "infra" / "bicep" / "deploy.sh",
        "scripts/e2e-local.sh": template / "scripts" / "e2e-local.sh",
        "infra/README-delivery-pack.md": template / "README.md",
    }

    commit_url = f"https://api.bitbucket.org/2.0/repositories/{workspace}/{slug}/src"
    headers = {"Accept": "application/json"}
    auth = (email, token)

    common_headers = bitbucket_headers(email, token)
    head = branch_head(workspace, slug, branch, common_headers)
    main_head = None
    for candidate in [main_branch, "main", "master"]:
        candidate = (candidate or "").strip()
        if not candidate:
            continue
        main_head = branch_head(workspace, slug, candidate, common_headers)
        if main_head:
            main_branch = candidate
            break
    repo_is_empty = head is None and main_head is None

    data = {
        "branch": branch,
        "message": f"chore({epic}): apply shopping-list delivery pack",
    }
    if head is None and not repo_is_empty:
        data["parents"] = main_head

    multipart = {}
    for dst, src in files_to_commit.items():
        multipart[dst] = (Path(dst).name, src.read_bytes())

    notes = f"# Epic Preparation\n\nEpic: {epic}\n\nThis repository was prepared with the shopping-list delivery pack for orchestrated delivery.\n"
    multipart["EPIC_PREPARED.md"] = ("EPIC_PREPARED.md", notes.encode("utf-8"))

    resp = requests.post(commit_url, headers=headers, auth=auth, data=data, files=multipart, timeout=60)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Bitbucket API commit failed: {resp.status_code} {resp.text[:300]}")


def main():
    parser = argparse.ArgumentParser(description="Prepare Bitbucket repository for epic delivery pack")
    parser.add_argument("--epic", required=True)
    parser.add_argument("--repo-slug", default="")
    parser.add_argument("--branch", default="")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    cfg = read_env(root / ".env")

    workspace = cfg.get("BITBUCKET_WORKSPACE", "").strip()
    email = cfg.get("BITBUCKET_EMAIL", "").strip()
    vault = cfg.get("AZURE_KEY_VAULT_NAME", "").strip()
    token_secret = cfg.get("BITBUCKET_API_TOKEN_SECRET_NAME", "bitbucket-api-token").strip()
    project_key = cfg.get("BITBUCKET_PROJECT_KEY", "").strip()

    if not workspace or not email or not vault:
        raise RuntimeError("Missing required .env values: BITBUCKET_WORKSPACE, BITBUCKET_EMAIL, AZURE_KEY_VAULT_NAME")

    token = get_kv_secret(vault, token_secret)
    if not token:
        raise RuntimeError("Bitbucket token is empty")

    epic_slug = args.epic.lower().replace("-", "")
    repo_slug = args.repo_slug.strip() or cfg.get("BITBUCKET_REPO_SLUG", "").strip() or f"{epic_slug}-shopping-list-app"
    branch = args.branch.strip() or f"epic/{args.epic.lower()}-delivery-pack"

    headers = bitbucket_headers(email, token)
    repo_data, created = ensure_repo(workspace, repo_slug, project_key, headers)

    clone_base = root / ".tmp"
    clone_base.mkdir(parents=True, exist_ok=True)
    clone_dir = clone_base / repo_slug
    if clone_dir.exists():
        shutil.rmtree(clone_dir)

    pushed_with_git = False
    try:
        encoded_token = quote(token, safe="")
        clone_url = f"https://x-token-auth:{encoded_token}@bitbucket.org/{workspace}/{repo_slug}.git"
        run(["git", "clone", clone_url, str(clone_dir)])
        run(["git", "config", "user.name", "Spec2Code Bot"], cwd=clone_dir)
        run(["git", "config", "user.email", email], cwd=clone_dir)
        run(["git", "checkout", "-B", branch], cwd=clone_dir)

        apply_script = root / "scripts" / "apply-shopping-list-delivery-pack.sh"
        run([str(apply_script), str(clone_dir)], cwd=root)

        notes_file = clone_dir / "EPIC_PREPARED.md"
        notes_file.write_text(
            f"# Epic Preparation\n\nEpic: {args.epic}\n\nThis repository was prepared with the shopping-list delivery pack for orchestrated delivery.\n",
            encoding="utf-8",
        )

        run(["git", "add", "."], cwd=clone_dir)
        status = run(["git", "status", "--porcelain"], cwd=clone_dir)
        if status.stdout.strip():
            run(["git", "commit", "-m", f"chore({args.epic}): apply shopping-list delivery pack"], cwd=clone_dir)
            run(["git", "push", "-u", "origin", branch], cwd=clone_dir)
        pushed_with_git = True
    except Exception:
        repo_default_branch = (repo_data.get("mainbranch") or {}).get("name", "").strip()
        main_branch = repo_default_branch or cfg.get("BITBUCKET_MAIN_BRANCH", "master").strip() or "master"
        commit_files_via_api(
            workspace=workspace,
            slug=repo_slug,
            branch=branch,
            main_branch=main_branch,
            email=email,
            token=token,
            epic=args.epic,
        )

    html_link = repo_data.get("links", {}).get("html", {}).get("href", f"https://bitbucket.org/{workspace}/{repo_slug}")
    pr_link = f"{html_link}/pull-requests/new?source={branch}"

    print(f"repo_created={created}")
    print(f"repo_slug={repo_slug}")
    print(f"branch={branch}")
    print(f"push_mode={'git' if pushed_with_git else 'api'}")
    print(f"repo_url={html_link}")
    print(f"pr_url={pr_link}")
    print(f"local_clone={clone_dir}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)
