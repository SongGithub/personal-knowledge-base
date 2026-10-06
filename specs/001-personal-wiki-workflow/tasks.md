# Tasks: Personal Wiki Workflow

**Input**: [spec.md](spec.md), [checklists/requirements.md](checklists/requirements.md)

**Status**: Not started, 2026-10-06. No implementation exists yet: the repository
contains no CLI for intake, review, approval, search, or checks. Work is blocked
on [plan.md](plan.md), which has not been written.

**Format**: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story from [spec.md](spec.md)

## Phase 1: Setup

- [ ] T001 Write the implementation plan in
  `specs/001-personal-wiki-workflow/plan.md`, covering the local CLI, vault
  discovery, and file layout for batches, the index, and the activity log.
- [ ] T002 Confirm the plan against the constitution (Principles I-VI) and
  record the constitution check in `plan.md`.

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: Shared pieces every user story depends on. No user story can be
implemented until this phase is complete.

- [ ] T003 Implement configurable vault discovery and `--vault` override in the
  local CLI (FR-001).
- [ ] T004 [P] Define the Source record model with origin, intake time, type,
  and a stable reference (FR-003).
- [ ] T005 [P] Define the Batch model with review status and source links.
- [ ] T006 Implement the append-only activity log for intake, review, and
  applied changes (FR-009).
- [ ] T007 Enforce that private source content and generated pages stay outside
  the repository, and that committed example data is synthetic (FR-014).

**Checkpoint**: Vault discovery, the core models, and the activity log work.

## Phase 3: User Story 1 - Review a source batch (P1) 🎯 MVP

**Goal**: The user selects Markdown files or saved web clips and receives one
proposed batch of wiki changes; nothing becomes canonical until approval.

**Independent test**: Process two synthetic sources, inspect and reject the
proposal, then repeat and approve it. Confirm the vault changes only after
approval and that the original sources never change.

- [ ] T008 [US1] Implement intake for Markdown files and saved web clips that
  preserves each source file unmodified (FR-002).
- [ ] T009 [US1] Generate one inspectable batch listing every proposed
  canonical page, index, and log change before approval (FR-004).
- [ ] T010 [US1] Link each proposed claim to a source passage or location
  (FR-003).
- [ ] T011 [US1] Implement approve and reject for the complete batch, leaving
  canonical content unchanged on rejection (FR-005).
- [ ] T012 [US1] Apply an approved batch consistently, or report what remains
  unapplied so recovery produces no duplicate entries (FR-006).
- [ ] T013 [US1] Detect changes to existing canonical pages on reprocessing and
  surface conflicts before an overwrite is possible (FR-007).
- [ ] T014 [P] [US1] Add synthetic-fixture tests for the approve and reject
  paths in `tests/`.

**Checkpoint**: One batch can be reviewed, rejected, and approved end to end.

## Phase 4: User Story 2 - Find and ask (P2)

**Goal**: The user browses a generated index and asks questions about the
approved wiki, with answers that make missing or conflicting evidence visible.

**Independent test**: Approve a small synthetic batch, browse each index section,
and ask one supported, one unsupported, and one conflicting question.

- [ ] T015 [US2] Generate an index that navigates approved entries across the
  domain index notes (FR-008, FR-010).
- [ ] T016 [US2] Implement keyword search over approved content (FR-010).
- [ ] T017 [US2] Implement questions that cite supporting approved notes and
  source evidence (FR-010, FR-011).
- [ ] T018 [US2] Distinguish supported claims, absent evidence, and conflicting
  evidence, and never cite unapproved drafts as canonical (FR-011).
- [ ] T019 [P] [US2] Add tests for supported, unsupported, and conflicting
  questions in `tests/`.

**Checkpoint**: The index is navigable and the three question classes behave.

## Phase 5: User Story 3 - Check the wiki (P3)

**Goal**: The user runs a local check and sees broken links, pages missing from
the index, and sources whose processing needs attention.

**Independent test**: Seed synthetic broken links, an orphan page, and an
interrupted batch; run the check and confirm each issue is reported without
changing vault content.

- [ ] T020 [US3] Implement a check command that reports broken links, approved
  pages missing from the index, and incomplete processing state (FR-012).
- [ ] T021 [US3] Ensure the check never edits vault content (FR-012).
- [ ] T022 [P] [US3] Add tests for seeded broken links, an orphan, and an
  interrupted batch in `tests/`.

## Phase 6: Integration and polish

- [ ] T023 Provide the same workflow to OpenClaw without defining a separate
  vault format (FR-013).
- [x] T024 [P] Publish a reusable vault instruction template without private
  vault data in `templates/vault/AGENTS.md` (FR-015).
- [x] T025 [P] Confirm the vault root guidance removes the default Obsidian
  welcome note and that the workflow reads root instructions first (FR-015).

## Dependencies & Execution Order

- Setup (Phase 1) must land before any implementation: `plan.md` does not exist.
- Foundational (Phase 2) blocks every user story.
- US1 (P1) is the MVP. US2 (P2) and US3 (P3) depend on Phase 2; US2 also needs
  approved pages to index.
- Phase 6 depends on the user stories it integrates.

## Notes

- [P] tasks touch different files and can run in parallel.
- Verify tests fail before implementing.
- Keep every committed fixture synthetic and every private path out of Git.
- Approved pages belong in `Wiki/` and pending review batches in
  `Resources/_Review/`; the remaining open questions are in the Review
  Questions of [spec.md](spec.md).
