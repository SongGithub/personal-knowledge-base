#!/usr/bin/env python3
"""Verify a deployed Google-authenticated MCP using the synthetic orchard note.

Requires interactive owner OAuth on first run; never accepts AWS keys or a token
on the command line. OAuth is handled by the maintained client implementation.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlsplit

from fastmcp import Client
from fastmcp.client.auth import OAuth
import httpx2


NOTE = "Resources/MCP Demo/Mock orchard.md"
FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/cloud-kb" / NOTE


async def verify(url):
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
    auth = OAuth(mcp_url=url, callback_port=8765, callback_host="localhost", client_name="KB mock proof")
    async with Client(url, auth=auth, timeout=30) as client:
        names = {tool.name for tool in await client.list_tools()}
        if not {"search_kb", "fetch_note"} <= names:
            raise RuntimeError("Required MCP tools are missing")
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
    asyncio.run(verify(parser.parse_args().url))
