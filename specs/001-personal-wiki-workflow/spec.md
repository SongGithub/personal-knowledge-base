# Feature Specification: Personal Wiki Workflow

**Feature Branch**: `main`

**Created**: 2026-10-03

**Status**: Draft for review

**Input**: A private, portable knowledge base that turns Markdown and web clips
into a cited wiki in the existing `KB` Obsidian vault. The first harness is
OpenClaw, supported by a small local CLI.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Review a source batch (Priority: P1)

The user selects one or more Markdown files or saved web clips and receives a
single proposed batch of wiki changes. The proposal shows the source of each
claim, all new or changed pages, and an overview of the batch. Nothing becomes
canonical until the user approves the batch.

**Why this priority**: The review boundary makes imported knowledge useful
without giving the assistant control over the canonical wiki.

**Independent Test**: Process two synthetic sources, inspect the proposal,
reject it, then repeat and approve it. Confirm the vault changes only after
approval and the original sources never change.

**Acceptance Scenarios**:

1. **Given** the `KB` vault is prepared, **When** the user opens its root,
   **Then** it contains the top-level content folders, a domain index note for
   each category, and AI-facing instructions instead of a competing top-level
   taxonomy.
2. **Given** two readable sources, **When** the user requests intake, **Then**
   one reviewable batch lists proposed page changes and links each claim to a
   source passage or location.
3. **Given** an unapproved batch, **When** the user rejects it, **Then** no
   canonical wiki page or index entry changes.
4. **Given** an approved batch, **When** changes are applied, **Then** the
   canonical pages, index, and activity log reflect the same batch.
5. **Given** a source was processed before, **When** it is processed again,
   **Then** existing user edits are shown as potential conflicts rather than
   silently overwritten.

---

### User Story 2 - Find and ask (Priority: P2)

The user browses a generated index and asks questions about the approved wiki.
Answers include links to supporting notes and make missing or conflicting
evidence visible.

**Why this priority**: The wiki must be navigable and useful after approval.

**Independent Test**: Approve a small synthetic batch, browse each index
section, and ask one supported, one unsupported, and one conflicting question.

**Acceptance Scenarios**:

1. **Given** approved pages, **When** the user opens the index, **Then** it
   provides navigation across the domain index notes nested under the vault's
   top-level folders and links to their approved entries.
2. **Given** a supported question, **When** the user asks it, **Then** the
   answer links to the relevant approved notes and source evidence.
3. **Given** no supporting evidence, **When** the user asks a question,
   **Then** the answer says the vault does not support a conclusion.
4. **Given** contradictory sources, **When** the user asks about that fact,
   **Then** the answer shows the disagreement and cites both sides.

---

### User Story 3 - Check the wiki (Priority: P3)

The user runs a local check and sees broken links, pages absent from the index,
and sources whose processing status needs attention.

**Why this priority**: Simple checks keep the wiki trustworthy as it grows.

**Independent Test**: Seed synthetic broken links, an orphan page, and an
interrupted batch; run the check and verify each issue is reported without
changing vault content.

**Acceptance Scenarios**:

1. **Given** a broken wiki link, **When** a check runs, **Then** the missing
   target and referring page are reported.
2. **Given** an approved page missing from the index, **When** a check runs,
   **Then** the page is reported as an orphan.
3. **Given** interrupted processing, **When** a check runs, **Then** the
   incomplete batch is identified for review.

### Edge Cases

- A source is unreadable, missing, or duplicated in the same batch.
- A web clip has no original URL or capture time.
- Two sources propose different values for one claim.
- Approval is interrupted while changes are being applied.
- A page or source has been edited since the proposal was generated.
- A requested question has only unapproved draft evidence.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The user MUST be able to configure the vault location without
  editing project files or exposing its path in the public repository.
- **FR-002**: The workflow MUST accept local Markdown files and saved web clips
  as initial source types from `Resources`, where unorganised material awaiting
  ingestion is kept. It MUST preserve each source file unmodified.
- **FR-003**: Each source record MUST include its origin, intake time, and a
  stable reference that proposed changes and answers can cite.
- **FR-004**: Intake MUST produce one inspectable batch that lists all proposed
  canonical page, index, and log changes before approval.
- **FR-005**: The user MUST be able to approve or reject the complete batch.
  Rejection MUST leave canonical content unchanged.
- **FR-006**: Approval MUST apply the batch consistently or report what remains
  unapplied so the user can recover without duplicate entries.
- **FR-007**: Reprocessing MUST detect changes to existing canonical pages and
  surface conflicts before an overwrite is possible.
- **FR-008**: The vault MUST keep its existing top-level folders: Ideas,
  Projects, Areas, Resources, Archive, Wiki, and Personal Facts. The owner's
  domain categories MUST be recorded as index notes nested inside those
  folders, and the index MUST navigate approved entries across those domains.
  Sources MUST live in `Resources`. Neither the top-level folders nor the
  domain layer may be replaced by a competing taxonomy.
- **FR-009**: An append-only activity log MUST record intake, approval or
  rejection, and applied page changes with references to the affected batch.
- **FR-010**: The user MUST be able to search approved content by keywords and
  ask questions that cite supporting approved notes and source evidence.
- **FR-011**: Answers MUST distinguish supported claims, absent evidence, and
  conflicting evidence. Unapproved drafts MUST not be cited as canonical facts.
- **FR-012**: A local check MUST report broken links, approved pages missing
  from the index, and incomplete processing state without editing the vault.
- **FR-013**: The user MUST have a small local CLI for intake, review, approval,
  search, questions, and checks. OpenClaw instructions MUST use that same
  workflow without defining a separate vault format.
- **FR-014**: Private source content and generated wiki pages MUST remain
  outside the repository; example data used in the repo MUST be synthetic.
- **FR-015**: The vault root MUST contain AI-facing instructions and the
  top-level content folders. The default Obsidian welcome note MUST be removed
  when these instructions replace it. The public repository MUST provide a
  reusable instruction template without containing private vault data. The
  OpenClaw workflow MUST read the vault's root instructions before working
  with it.

### Key Entities

- **Source**: Immutable item kept in `Resources`, with origin, intake time,
  type, and stable reference.
- **Batch**: A group of proposed changes with review status and source links.
- **Wiki page**: Approved knowledge entry with evidence links.
- **Index entry**: Link to an approved page reached through a domain index note.
- **Activity event**: Append-only record of intake, review, or applied change.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a demonstration with two synthetic sources, the user can
  inspect and approve or reject one complete batch in under five minutes.
- **SC-002**: In the same demonstration, 100% of new factual claims in proposed
  pages have a usable source reference.
- **SC-003**: Rejecting a batch changes zero canonical pages or index entries.
- **SC-004**: After approval, all generated index links in the demonstration
  resolve, and the activity log identifies every applied page change.
- **SC-005**: A set of three questions produces cited support, an explicit
  evidence gap, and an explicit conflict respectively.
- **SC-006**: A seeded broken link, orphan page, and incomplete batch are all
  reported by one check.

## Assumptions

- The `KB` vault keeps seven top-level folders: `Ideas`, `Projects`, `Areas`,
  `Resources`, `Archive`, `Wiki`, and `Personal Facts`. The owner's domain
  categories are recorded as index notes nested inside them, and the
  `Personal Facts` folder is itself the home of the personal-facts domain. The
  vault folders are currently Chinese; a link-safe migration to English names
  is planned but not yet approved.
- `AGENTS.md` is the file name used for the root AI-facing instructions; this
  matches the naming convention observed in the user's OpenClaw workspaces.
- Unorganised material awaiting ingestion and original source files belong in
  `Resources`, with pending review batches in `Resources/_Review/`. Approved
  pages belong in `Wiki/`, whose index note is the vault entry point.
  Preserved source snapshots stay unmodified in `Archive/`.
- Web clips are saved local files or text with an origin URL when available.
  The workflow does not need to fetch live pages in the first release.
- The first release serves one user on one Mac. Sync and concurrent edits
  across devices are outside this feature.
- The CLI and OpenClaw adapter work over the same ordinary Markdown vault.
- Keyword search is sufficient for the first release; semantic retrieval is
  deferred until usage shows a need.

## Review Questions

- Resolved by the vault: approved generated pages belong in `Wiki/`, and
  pending review batches live in `Resources/_Review/`.
- Open: should rejected batches remain in an audit area, or may they be
  discarded after the rejection event is recorded?
- Open: should `Archive/` source snapshots keep their original filenames when
  the vault is migrated to English names? Imported sources must stay
  unmodified, which argues for leaving preserved snapshots as they are.
