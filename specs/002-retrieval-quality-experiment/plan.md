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
