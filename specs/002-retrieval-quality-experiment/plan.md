# Implementation Plan: Local Retrieval Quality Experiment

**Date**: 2026-10-05 | **Spec**: [spec.md](spec.md)

## Design

Python standard library CLI. Discover `KB` under the Obsidian iCloud container
or accept `--vault`; never write its absolute path to Git. Chunk notes by
paragraph/heading into bounded text. SQLite stores paths, chunk text, and
float32 vectors in a private local database. The cached BGE-M3 multilingual
model runs through local oMLX over loopback only. Lexical uses deterministic
Unicode token BM25 (including Chinese character bigrams); vector uses exact
cosine over stored vectors; hybrid uses weighted reciprocal-rank fusion plus
an explicit near-tie authority gate. Aggregate chunk ranks
to note ranks, with normalized relative path as final tie break.

## Constitution check

- 0.3.0 draft amendment documents need and experimental exception.
- Vault is read-only; SQLite and real cases/report outside Git.
- No hosted service or network content transmission.
- Production adoption remains a later reviewed decision.

## Verification

Use synthetic fixtures for deterministic ranking, authority and metric tests.
Then run real-vault indexing and benchmark, inspect per-case failures, verify
ignored private artifacts, and commit only public code/specs/fixtures.

## Incremental reconciliation algorithm (added 2026-10-07)

Refresh replaces whole-vault rebuilds as the default path:

1. **Vault scan** - enumerate Markdown notes (never editing them) and compute a
   SHA-256 per note.
2. **Compare per-note hashes** - load indexed note paths and hashes from SQLite
   and classify each note as added, changed, deleted, or unchanged.
3. **Delete stale notes** - remove note and chunk rows for deleted paths.
4. **Reindex changed/new notes** - recompute authority, upsert the note row, drop
   the old chunks for that path, and rechunk only that note.
5. **Preserve vectors** - leave chunks and vectors of unchanged notes untouched
   and embed only the newly created chunks.
6. **Update metadata** - record model, chunker, authority rules, index schema
   version, source hash and override hash.
7. **Integrity check** - confirm no chunk has a missing vector; a missing vector
   or an incompatible model/chunker/schema forces a full rebuild instead.

The compatibility gate keeps the store disposable: a model, chunker or schema
change, or a corrupt or partial index, triggers one complete rebuild. Authority
changes never re-embed; they update tiers in place.
