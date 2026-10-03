# Personal Knowledge Base

A private, portable wiki workflow for turning sources into reviewable knowledge
pages and answering questions with evidence. The first release targets one user,
an Obsidian vault, a small local CLI, and OpenClaw.

This repository contains the project specification and, later, code and
templates. Private sources and generated wiki pages belong in the user's vault,
outside Git.

## Current status

Specification draft. No application code or vault content has been added. The
local `KB` vault was inspected on 2026-10-03 and contained only Obsidian's
default welcome note. The user identified Ideas, Projects, Areas, Resources,
Archive, and Wiki as the wiki folders. The specification records this layout;
the location of those folders still needs to be reconciled with the observed
local vault before implementation.

Review the [constitution](.specify/memory/constitution.md) and
[MVP feature specification](specs/001-personal-wiki-workflow/spec.md) before
creating the implementation plan or tasks.

## Development workflow

The repository includes GitHub Spec Kit with Codex integration. Work proceeds
through constitution, specification, plan, tasks, and implementation, with
review at each boundary. Keep synthetic examples in the repo and private data
in the vault.
