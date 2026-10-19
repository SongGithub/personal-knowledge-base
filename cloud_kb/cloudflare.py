"""Narrow Cloudflare DNS automation for the owner's MCP hostname."""
import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ZONE = "midu.com.au"
MCP_HOST = "mcp.midu.com.au"
API = "https://api.cloudflare.com/client/v4"


class CloudflareDns:
    """Create only the DNS-only CNAMEs required to validate and publish the MCP."""

    def __init__(self, token, opener=urlopen):
        if not isinstance(token, str) or not token.strip():
            raise ValueError("cloudflare_token_required")
        self.token, self.opener = token.strip(), opener
        self.zone_id = self._zone_id()

    def _request(self, method, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(API + path, data=data, method=method, headers={
            "Authorization": "Bearer " + self.token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        try:
            with self.opener(request, timeout=20) as response:
                result = json.loads(response.read(1_000_000))
        except (HTTPError, URLError, TimeoutError, OSError, ValueError):
            raise RuntimeError("cloudflare_api_unavailable") from None
        if not isinstance(result, dict) or not result.get("success"):
            raise RuntimeError("cloudflare_api_rejected_request")
        return result.get("result")

    def _zone_id(self):
        result = self._request("GET", "/zones?" + urlencode({"name": ZONE, "status": "active", "per_page": 50}))
        zones = [zone for zone in (result or []) if zone.get("name") == ZONE]
        if len(zones) != 1 or not zones[0].get("id"):
            raise RuntimeError("cloudflare_zone_not_unique_or_active")
        return zones[0]["id"]

    def ensure_cname(self, name, target):
        canonical_name = name.rstrip(".").lower()
        canonical_target = target.rstrip(".").lower()
        if (canonical_name != MCP_HOST and not canonical_name.endswith("." + MCP_HOST) or
                not canonical_target or any(c.isspace() for c in canonical_name + canonical_target)):
            raise ValueError("cloudflare_cname_out_of_scope")
        query = urlencode({"name": canonical_name, "per_page": 100})
        path = f"/zones/{self.zone_id}/dns_records?{query}"
        records = self._request("GET", path) or []
        if len(records) > 1:
            raise RuntimeError("cloudflare_dns_conflict")
        desired = {"type": "CNAME", "name": canonical_name, "content": canonical_target,
                   "ttl": 1, "proxied": False, "comment": "Managed by Personal KB MCP pipeline"}
        if records:
            record = records[0]
            if (record.get("type") != "CNAME" or
                    record.get("content", "").rstrip(".").lower() != canonical_target):
                raise RuntimeError("cloudflare_dns_conflict")
            if record.get("proxied") is False and record.get("ttl") == 1:
                return "unchanged"
            self._request("PATCH", f"/zones/{self.zone_id}/dns_records/{record['id']}", desired)
            return "updated"
        self._request("POST", f"/zones/{self.zone_id}/dns_records", desired)
        return "created"


def ensure_certificate_validated(acm, dns, certificate_arn, *, wait_seconds=900, poll_seconds=10):
    """Publish ACM's DNS validation CNAME and wait until its cert is issued."""
    deadline = time.monotonic() + wait_seconds
    while True:
        certificate = acm.describe_certificate(CertificateArn=certificate_arn)["Certificate"]
        if certificate.get("DomainName") != MCP_HOST or certificate.get("Type") != "AMAZON_ISSUED":
            raise RuntimeError("custom_domain_certificate_mismatch")
        status = certificate.get("Status")
        if status == "ISSUED":
            return
        if status not in {"PENDING_VALIDATION", "PENDING_ISSUANCE"}:
            raise RuntimeError("custom_domain_certificate_not_issuable")
        options = [item for item in certificate.get("DomainValidationOptions", [])
                   if item.get("DomainName", "").lower() == MCP_HOST]
        record = options[0].get("ResourceRecord") if len(options) == 1 else None
        if record:
            if record.get("Type") != "CNAME" or not record.get("Name", "").lower().endswith("." + MCP_HOST + "."):
                raise RuntimeError("custom_domain_validation_record_mismatch")
            dns.ensure_cname(record["Name"], record["Value"])
        if time.monotonic() >= deadline:
            raise TimeoutError("custom_domain_certificate_validation_timeout")
        time.sleep(poll_seconds)


def verify_custom_endpoint(url, *, opener=urlopen, wait_seconds=180, poll_seconds=5):
    """Verify custom hostname liveness and its unauthenticated MCP challenge."""
    deadline = time.monotonic() + wait_seconds
    health_url = url.removesuffix("/mcp").removesuffix("/healthz") + "/healthz"
    while True:
        try:
            with opener(health_url, timeout=15) as health:
                if health.status != 200:
                    raise RuntimeError("custom_domain_health_failed")
            request = Request(url, data=b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}', headers={
                "Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
            try:
                with opener(request, timeout=15):
                    raise RuntimeError("custom_domain_mcp_auth_not_enforced")
            except HTTPError as error:
                if error.code != 401 or not error.headers.get("WWW-Authenticate", "").startswith("Bearer"):
                    raise RuntimeError("custom_domain_mcp_auth_check_failed") from None
            return
        except (HTTPError, URLError, TimeoutError, OSError):
            if time.monotonic() >= deadline:
                raise TimeoutError("custom_domain_dns_or_tls_not_ready") from None
            time.sleep(poll_seconds)
