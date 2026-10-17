"""Fail-closed configuration for the Google-protected cloud service."""
from dataclasses import dataclass
import json
import os
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    base_url: str
    vault_bucket: str
    index_bucket: str
    control_table: str
    owner_sub: str
    secret_arn: str
    client_redirect_uris: tuple[str, ...]

    @classmethod
    def from_environment(cls):
        values = {name: os.environ[f"PKB_{name.upper()}"] for name in (
            "base_url", "vault_bucket", "index_bucket", "control_table",
            "owner_sub", "secret_arn",
        )}
        url = urlsplit(values["base_url"])
        if (url.scheme != "https" or not url.hostname or url.username or
                url.password or url.path not in ("", "/") or url.query or url.fragment):
            raise ValueError("PKB_BASE_URL must be an HTTPS origin")
        if not all(values.values()):
            raise ValueError("All cloud service settings are required")
        redirects = json.loads(os.environ["PKB_CLIENT_REDIRECT_URIS"])
        if (not isinstance(redirects, list) or not redirects or
                any(not isinstance(uri, str) or "*" in uri for uri in redirects)):
            raise ValueError("Configure exact OAuth client redirect URIs")
        for uri in redirects:
            callback = urlsplit(uri)
            local = callback.hostname in {"127.0.0.1", "localhost", "::1"}
            if (callback.scheme != "https" and not (local and callback.scheme == "http")) or callback.fragment:
                raise ValueError("OAuth redirects require HTTPS or an exact loopback callback")
        return cls(**values, client_redirect_uris=tuple(redirects))
