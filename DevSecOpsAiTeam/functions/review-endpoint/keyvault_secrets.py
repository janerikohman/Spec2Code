"""Centralised Azure Key Vault secret retrieval for the review-endpoint runtime.

All secrets consumed by this service MUST be retrieved via get_secret() or the
convenience accessors below.  Hardcoded credentials are forbidden by:

  RULE_15_SECRETS_IN_KEY_VAULT

Authentication topology (mirrors .env.example):

  Jira + Confluence  →  JIRA-EMAIL  +  JIRA-API-TOKEN
                        (same key for both — RULE_16_JIRA_CONFLUENCE_SHARED_AUTH)

  Bitbucket          →  BITBUCKET-USERNAME  +  BITBUCKET-APP-PASSWORD
                        (separate credentials — RULE_17_BITBUCKET_SEPARATE_AUTH)

Usage:
    from keyvault_secrets import get_secret, jira_email, jira_api_token
    token = jira_api_token()

The Key Vault name is resolved from the environment variable AZURE_KEY_VAULT_NAME,
which is set as an Application Setting on the Azure Function App (never hardcoded).

When running locally, set AZURE_KEY_VAULT_NAME in your local.settings.json and
authenticate with `az login` so DefaultAzureCredential picks up the CLI token.
"""
from __future__ import annotations

import os
import logging
from functools import lru_cache

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

logger = logging.getLogger(__name__)

_VAULT_NAME_ENV = "AZURE_KEY_VAULT_NAME"


@lru_cache(maxsize=1)
def _client() -> SecretClient:
    """Return a cached SecretClient backed by DefaultAzureCredential.

    Raises EnvironmentError if AZURE_KEY_VAULT_NAME is not set.
    """
    vault_name = os.environ.get(_VAULT_NAME_ENV, "").strip()
    if not vault_name:
        raise EnvironmentError(
            f"Environment variable '{_VAULT_NAME_ENV}' is not set. "
            "Set it to your Key Vault name in Application Settings (never hardcode it)."
        )
    vault_url = f"https://{vault_name}.vault.azure.net/"
    logger.debug("Connecting to Key Vault: %s", vault_url)
    return SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())


def get_secret(name: str) -> str:
    """Fetch *name* from Azure Key Vault.

    RULE_15_SECRETS_IN_KEY_VAULT: This is the ONLY approved way to read secrets.
    Results are cached in-process for the lifetime of the function host.

    Args:
        name: The Key Vault secret name (e.g. "JIRA-API-TOKEN").

    Returns:
        The secret value as a string.

    Raises:
        azure.core.exceptions.ResourceNotFoundError: if the secret does not exist.
        EnvironmentError: if AZURE_KEY_VAULT_NAME is not configured.
    """
    value = _client().get_secret(name).value
    if not value:
        raise ValueError(f"Key Vault secret '{name}' exists but is empty.")
    return value


# ---------------------------------------------------------------------------
# Convenience accessors — use these everywhere, never inline get_secret() calls
# with raw secret names.
# ---------------------------------------------------------------------------

def jira_email() -> str:
    """Shared email for Jira AND Confluence (RULE_16_JIRA_CONFLUENCE_SHARED_AUTH).

    The same address is used to authenticate both services.
    Key Vault secret name: JIRA-EMAIL
    """
    return get_secret("JIRA-EMAIL")


def jira_api_token() -> str:
    """Shared API token for Jira AND Confluence (RULE_16_JIRA_CONFLUENCE_SHARED_AUTH).

    The same API token authenticates both services — do not create separate tokens.
    Key Vault secret name: JIRA-API-TOKEN
    """
    return get_secret("JIRA-API-TOKEN")


def bitbucket_username() -> str:
    """Bitbucket account username (RULE_17_BITBUCKET_SEPARATE_AUTH).

    Distinct from Jira/Confluence credentials — never mix them.
    Key Vault secret name: BITBUCKET-USERNAME
    """
    return get_secret("BITBUCKET-USERNAME")


def bitbucket_app_password() -> str:
    """Bitbucket app-password (RULE_17_BITBUCKET_SEPARATE_AUTH).

    Generated in Bitbucket → Account settings → App passwords.
    Distinct from the Jira/Confluence API token.
    Key Vault secret name: BITBUCKET-APP-PASSWORD
    """
    return get_secret("BITBUCKET-APP-PASSWORD")


def bitbucket_workspace() -> str:
    """Bitbucket workspace slug (RULE_17_BITBUCKET_SEPARATE_AUTH).

    Key Vault secret name: BITBUCKET-WORKSPACE
    """
    return get_secret("BITBUCKET-WORKSPACE")
