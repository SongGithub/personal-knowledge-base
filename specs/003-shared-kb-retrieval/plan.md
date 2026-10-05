# Implementation Plan: Shared Local KB Retrieval

**Date**: 2026-10-05 | **Spec**: [spec.md](spec.md)

## Design

Keep the retrieval engine, private SQLite index, and authority/ranking policy
in a vendor-neutral Python package. Add a read-only local service interface;
the first adapter is stdio MCP for OpenClaw. Clients call `search_kb` and
`fetch_note`, never SQLite directly. Search responses carry relative paths,
authority tier, excerpt, and provenance. Resolve paths under the configured
vault root and reject traversal. Expose no SQL or write tools.

OpenClaw is a client adapter only. ChatGPT connectivity is a separate future
adapter/bridge with its own authentication and disclosure; it must not become a
dependency of the local service. Keep embeddings and index generation local and
keep the SQLite file outside iCloud and the vault. Preserve a local CLI path for
benchmarking and direct use.

## Constitution check

- Proposed amendment 0.4.0 permits an owner-approved local retrieval service
  while keeping Markdown canonical and hosted storage out of scope.
- Client adapters are harness-specific; vault data and ranking behavior remain
  portable and vendor neutral.
- Hosted-model excerpts require explicit user action and a clear disclosure.
- Real vault content, paths, cases, indexes, and embeddings remain outside Git.

## Verification

Use synthetic fixtures to verify MCP tool schema, CLI/service parity, stale or
missing-index behavior, authority ordering, path traversal rejection, and
read-only surface. Probe the configured OpenClaw connection. Do not run against
the real vault or transmit real excerpts while validating the public fixture.
