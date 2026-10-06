<!--
Sync impact report
- Initial proposal: template -> 0.1.0 draft.
- Added principles: Privacy; Evidence; Human control; Portability; Small increments.
- Added sections: Product boundaries; Development workflow.
- 2026-10-05 amendment proposal: replace the six generic top-level folders with
  the owner's seven domain categories; update the feature specification,
  templates, vault guidance, and index requirements accordingly.
- 2026-10-05 retrieval experiment amendment: permit disposable, fully local
  semantic retrieval for a measured comparison with lexical search.
- 2026-10-05 shared retrieval amendment: owner approved implementation of a
  vendor-neutral local retrieval service over the rebuildable SQLite index,
  with client-specific connectivity kept in separate adapters. Overall
  constitution ratification remains pending review.
- 2026-10-06 naming and structure correction: Principle VI is rewritten as a
  domain index layer nested inside the vault's existing top-level folders. The
  2026-10-05 amendment proposal above wrongly described the seven domain
  categories as top-level folders replacing the generic taxonomy; the owner's
  vault keeps `Ideas`, `Projects`, `Areas`, `Resources`, `Archive`, `Wiki`, and
  `Personal Facts` at the top level. The domain categories are recorded in
  English (`Infrastructure`, `Personal Facts`, `Investments`, `Family Affairs`,
  `Books and Publications`, `Media Content`, `Personal Health Records`) as the
  target naming; the vault folders are still Chinese and a separate link-safe
  migration is planned.
- Ratification remains pending user review.
-->
# Personal Knowledge Base Constitution

## Core Principles

### I. Private by Default

Private sources and generated knowledge MUST stay in the user's Obsidian vault. The
public repository MUST contain only code, templates, synthetic examples, and
project documentation. No feature may transmit vault content to a service without
an explicit user action. This keeps the repository safe to share.

### II. Evidence and Provenance

Imported sources MUST remain unmodified. Every proposed knowledge change MUST
identify its source and supporting passage or link. Answers MUST cite supporting
notes and flag absent or conflicting evidence. A reader must be able to trace a
claim to its source.

### III. Human Control

Canonical wiki pages MUST change only after the user explicitly approves a
proposed batch. Drafts MUST be inspectable before approval, and accepted changes
MUST be recorded so they can be understood and reversed. Reprocessing a source
MUST not silently overwrite user edits.

### IV. Portable Knowledge

The vault format MUST use ordinary directories and Markdown. Harness-specific
instructions MUST be isolated from the vault format so another AI harness can
use the same knowledge without migration. Notes MUST remain readable without
this project's tools.

### V. Small, Verifiable Increments

The MVP MUST use the simplest workflow that meets the approved specification.
Each capability MUST have an observable acceptance check, including failure
cases. Hosted services and production semantic retrieval require a separate
documented need and amendment. A local retrieval experiment MAY use disposable
vector storage after its need, privacy boundary, benchmark, and exit criteria
are specified. Markdown MUST remain canonical and indexes MUST be rebuildable.
Private content MUST NOT be sent to an external embedding service without
explicit user approval. Experiment results MUST justify any later adoption.
A local retrieval service over a local, rebuildable SQLite index MAY be adopted
for cross-client access after a separate specification defines its privacy,
authority, and availability behavior. The retrieval core MUST NOT depend on a
single AI vendor. Client protocols and connectivity bridges MUST remain
adapters around the core. Each client MUST receive only the retrieved notes
needed for that request; sending those excerpts to a hosted model remains an
explicit user action and must be made clear. Hosted storage is outside this
amendment.

### VI. Domain Index Layer

The vault MUST keep its existing top-level folders - `Ideas`, `Projects`,
`Areas`, `Resources`, `Archive`, `Wiki`, and `Personal Facts` - and MUST NOT
replace them with a competing top-level taxonomy. The owner's domain categories
are recorded as index notes nested inside those folders, so that every domain
has one discoverable entry point. Sources and pending intake live in
`Resources`; `Areas` holds ongoing responsibilities; `Projects` holds bounded
work; `Archive` preserves source snapshots unmodified. The vault index MUST
make every domain category discoverable, and category-specific subfolders MAY
be used where they improve retrieval.

## Product Boundaries

The first release serves one user on one Mac with the existing `KB` Obsidian
vault. The initial sources are Markdown files and web clips. The first harness
is OpenClaw. Video transcription, hosted accounts, subscription billing, and
cross-device conflict resolution are outside the MVP. The vault path MUST be
configurable and never hard-coded to one user's home directory.

## Development Workflow

Use the repository's Spec Kit artifacts in order: constitution, feature
specification, implementation plan, tasks, then implementation. Review each
artifact before advancing to the next phase. Keep private vault contents out
of Git and use synthetic fixtures for demonstrations and tests. Verify privacy
boundaries and approval behavior before marking a capability complete.

## Governance

Changes to these principles require a documented amendment, a reason, and user
review before dependent specifications or code are updated. Use semantic
versions: major for incompatible principle changes, minor for new or materially
expanded principles, and patch for clarifications. Every feature review MUST
check its specification and implementation against this constitution. This
initial draft is proposed for review and is not yet ratified.

**Version**: 0.5.0 (draft) | **Ratified**: pending review | **Last Amended**: 2026-10-06
