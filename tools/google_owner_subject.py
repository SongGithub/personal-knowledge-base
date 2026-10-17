#!/usr/bin/env python3
"""Discover the owner's stable Google subject through a private loopback login.

Run only after approving the dedicated Google client. No token/code is printed
or persisted. The existing maintained Google verifier checks token audience,
scopes and expiry against Google before saving the private owner binding.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import secrets
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

from authlib.integrations.requests_client import OAuth2Session
from fastmcp.server.auth.providers.google import GoogleTokenVerifier


CALLBACK = "http://localhost:8766/google/callback"
SCOPES = ["openid", "https://www.googleapis.com/auth/userinfo.email"]


def private_write(path, text):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(text)


def discover(client_file, output, authorization_file):
    config = json.loads(client_file.read_text())["web"]
    if CALLBACK not in config.get("redirect_uris", []):
        raise ValueError("Dedicated client must register the exact owner callback")
    if output.exists() or authorization_file.exists():
        raise ValueError("Choose new private output paths; existing files are preserved")
    verifier = secrets.token_urlsafe(48)
    oauth = OAuth2Session(config["client_id"], config["client_secret"],
                          scope=SCOPES, redirect_uri=CALLBACK,
                          code_challenge_method="S256")
    url, state = oauth.create_authorization_url(
        "https://accounts.google.com/o/oauth2/v2/auth", code_verifier=verifier,
        nonce=secrets.token_urlsafe(32), prompt="select_account")
    result = {}

    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Callback paths contain authorization codes.

        def do_GET(self):
            parsed = urlsplit(self.path)
            values = parse_qs(parsed.query)
            if (parsed.path != "/google/callback" or
                    self.headers.get("Host") != "localhost:8766" or
                    values.get("state") != [state] or
                    len(values.get("code", [])) != 1):
                self.send_error(400, "Invalid OAuth callback")
                return
            result["code"] = values["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(b"Google callback received. Return to Codex for verification.")

    with HTTPServer(("127.0.0.1", 8766), Callback) as server:
        server.timeout = 1
        private_write(authorization_file, url)
        print(json.dumps({"status": "awaiting_owner_login", "authorization_file": str(authorization_file)}), flush=True)
        deadline = time.monotonic() + 300
        while "code" not in result and time.monotonic() < deadline:
            server.handle_request()
    if "code" not in result:
        raise RuntimeError("No valid owner callback received")
    token = oauth.fetch_token("https://oauth2.googleapis.com/token",
                              code=result.pop("code"), code_verifier=verifier, timeout=30)
    verified = asyncio.run(GoogleTokenVerifier(required_scopes=SCOPES,
                            audience=config["client_id"]).verify_token(token["access_token"]))
    if (verified is None or not verified.claims.get("sub") or
            not verified.claims.get("email") or
            verified.claims.get("email_verified") not in (True, "true")):
        raise RuntimeError("Google identity did not pass owner verification")
    private_write(output, json.dumps({"sub": verified.claims["sub"],
                                     "email": verified.claims["email"]}))
    oauth.close()
    print(json.dumps({"status": "verified", "owner_file": str(output)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--authorization-file", type=Path, required=True)
    args = parser.parse_args()
    discover(args.client_file, args.output, args.authorization_file)
