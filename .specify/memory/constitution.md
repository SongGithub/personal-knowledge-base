<!--
Sync impact report
- Initial proposal: template -> 0.1.0 draft.
- Added principles: Privacy; Evidence; Human control; Portability; Small increments.
- Added sections: Product boundaries; Development workflow.
- Follow-up: Ratification awaits user review.
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
cases. Hosted services, vector storage, and semantic retrieval require a
separate documented need and amendment.

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

**Version**: 0.1.0 (draft) | **Ratified**: pending review | **Last Amended**: 2026-10-03
