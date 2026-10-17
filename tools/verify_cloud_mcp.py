#!/usr/bin/env python3
"""Verify a deployed Google-authenticated MCP using the synthetic orchard note.

Requires interactive owner OAuth on first run. The optional owner-admin grant
setup accepts private file paths; never pass credential values on the command
line. OAuth is handled by the maintained client implementation.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import time
import sys
from urllib.parse import urlsplit

from fastmcp import Client
from fastmcp.client.auth import OAuth
import httpx2


NOTE = "Resources/MCP Demo/Mock orchard.md"
FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/cloud-kb" / NOTE
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def provision_mock_grant(session, url, owner_file, client_id):
    """Explicit owner-admin step; MCP clients never receive these AWS credentials."""
    from botocore.exceptions import ClientError

    owner = json.loads(owner_file.read_text())["sub"]
    cfn = session.client("cloudformation")
    outputs = lambda name: {x["OutputKey"]: x["OutputValue"] for x in
                           cfn.describe_stacks(StackName=name)["Stacks"][0]["Outputs"]}
    trust, foundation = outputs("pkb-dev-bootstrap"), outputs("pkb-dev-foundation")
    expected = f'https://{trust["HttpApiId"]}.execute-api.ap-southeast-2.amazonaws.com/mcp'
    if url != expected or foundation["ControlTableName"] != "pkb-dev-control":
        raise ValueError("Owner grant is restricted to the deployed dev MCP")
    config = session.client("lambda").get_function_configuration(FunctionName="pkb-dev-api")
    if config["Environment"]["Variables"]["PKB_OWNER_SUB"] != owner:
        raise ValueError("Verified owner does not match deployed owner binding")
    if not client_id:
        raise ValueError("The authenticated SDK must supply its registered client identity")
    item = {"PK": "GRANT#" + owner, "SK": "CLIENT#" + client_id,
            "Revoked": False, "ExpiresAt": int(time.time()) + 1800,
            "Scopes": ["kb:read"], "Prefixes": [NOTE], "SyntheticOnly": True}
    table = session.resource("dynamodb").Table("pkb-dev-control")
    try:
        table.put_item(Item=item, ConditionExpression="attribute_not_exists(PK)")
    except ClientError as error:
        if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        existing = table.get_item(Key={"PK": item["PK"], "SK": item["SK"]}, ConsistentRead=True).get("Item", {})
        if (not existing.get("SyntheticOnly") or existing.get("Revoked", True) or
                existing.get("Prefixes") != [NOTE] or existing.get("Scopes") != ["kb:read"] or
                int(existing.get("ExpiresAt", 0)) <= time.time()):
            raise RuntimeError("Existing client grant is preserved; owner review required") from None


async def verify(url, *, aws_env_file=None, owner_file=None, authorization_file=None):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.path != "/mcp" or
            parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError("Use the deployed HTTPS /mcp endpoint without credentials")
    # Do not follow an auth redirect and mistake a login page for an MCP response.
    async with httpx2.AsyncClient(follow_redirects=False, timeout=30) as http:
        response = await http.post(url, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                                   headers={"Accept": "application/json, text/event-stream"})
        if response.status_code not in (401, 403):
            raise RuntimeError("Unauthenticated MCP access was not rejected")
    started = time.monotonic()
    if (aws_env_file is None) != (owner_file is None):
        raise ValueError("Explicit mock grant setup requires both private owner and AWS files")
    if authorization_file is not None:
        from tools.google_owner_subject import private_write

        class BrowserOAuth(OAuth):
            async def redirect_handler(self, authorization_url):
                private_write(authorization_file, authorization_url)
                print(json.dumps({"status": "awaiting_owner_login", "authorization_file": str(authorization_file)}), flush=True)

        provider = BrowserOAuth
    else:
        provider = OAuth
    auth = provider(mcp_url=url, callback_port=8765, callback_host="localhost", client_name="KB mock proof")
    async with Client(url, auth=auth, timeout=30) as client:
        names = {tool.name for tool in await client.list_tools()}
        if not {"search_kb", "fetch_note"} <= names:
            raise RuntimeError("Required MCP tools are missing")
        if owner_file is not None:
            from tools.aws_session import session_from_file
            await asyncio.to_thread(provision_mock_grant, session_from_file(aws_env_file),
                                    url, owner_file, auth.context.client_info.client_id)
        search = (await client.call_tool("search_kb", {"query": "citrus-lantern-742", "strategy": "lexical"})).data
        matches = [item for item in search["results"] if item["path"] == NOTE]
        if not matches or matches[0]["freshness"] != "current":
            raise RuntimeError("Synthetic fixture is missing or stale in retrieval")
        fetched = (await client.call_tool("fetch_note", {"path": NOTE, "max_chars": 20_000})).data
        expected = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        if (fetched["sha256"] != expected or fetched["truncated"] or
                fetched["content"].encode() != FIXTURE.read_bytes() or not fetched["revision"]):
            raise RuntimeError("Fetched Markdown does not match the synthetic source")
    # No URLs, owner/client identifiers, credentials or private excerpts in output.
    print(json.dumps({"status": "passed", "transport": "HTTPS MCP", "auth": "OAuth",
                      "unauthenticated_denied": True, "search_and_fetch": True,
                      "mock_sha256": expected, "seconds_including_auth": round(time.monotonic() - started, 3)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--aws-env-file", type=Path, help="Owner-only opt-in to provision a 30-minute mock-note grant")
    parser.add_argument("--owner-file", type=Path)
    parser.add_argument("--authorization-file", type=Path, help="Private URL file for controlled browser login")
    args = parser.parse_args()
    asyncio.run(verify(args.url, aws_env_file=args.aws_env_file, owner_file=args.owner_file,
                       authorization_file=args.authorization_file))
