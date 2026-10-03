# Personal Knowledge Base

A private, portable wiki workflow for turning sources into reviewable knowledge
pages and answering questions with evidence. The first release targets one user,
an Obsidian vault, a small local CLI, and OpenClaw.

This repository contains the project specification and, later, code and
templates. Private sources and generated wiki pages belong in the user's vault,
outside Git.

## Current status

Specification draft. No application code or private vault content has been
added to this repository. The `KB` vault was prepared on 2026-10-03 with
Ideas, Projects, Areas, Resources, Archive, and Wiki as its top-level layout.
A public template for the vault's AI instructions is in
[`templates/vault/AGENTS.md`](templates/vault/AGENTS.md).

Review the [constitution](.specify/memory/constitution.md) and
[MVP feature specification](specs/001-personal-wiki-workflow/spec.md) before
creating the implementation plan or tasks.

## Development workflow

The repository includes GitHub Spec Kit with Codex integration. Work proceeds
through constitution, specification, plan, tasks, and implementation, with
review at each boundary. Keep synthetic examples in the repo and private data
in the vault.
