# Vault English migration plan

**Status**: Proposed, 2026-10-06. Not approved and not started. No vault file
has been renamed.

**Goal**: Give the `KB` vault English folder and note names, so the repository
documentation and the vault use one vocabulary. The structure does not change:
the top-level folders and the nested domain index layer stay exactly where they
are. This is a renaming migration, not a reorganisation.

## Scope

Only the vault's live area is in scope. Preserved source snapshots are excluded.

| Scope | Count | Action |
|---|---|---|
| Live notes with Chinese names | 11 | rename |
| Chinese-named folders in the live area | 7 | rename |
| Wikilink targets affected | ~22 distinct | update |
| Notes under `Archive/` source snapshots | 77 | **excluded** |
| Folders under `Archive/` source snapshots | 9 | **excluded** |

`Archive/` holds imported source snapshots. Constitution Principle II and FR-002
require imported sources to remain unmodified, so renaming them is out of scope.
That also removes the largest block of link churn: 38 of the 60 distinct Chinese
wikilink targets point into `Archive/`.

Of the targets outside `Archive/`, the five category folders account for only 6
links. The rest are ordinary notes; some are written as bare names that Obsidian
resolves into `Archive/` by shortest path and are therefore unaffected.

## Category mapping

The five live category folders keep their current position and take English
names:

| Current folder | Target |
|---|---|
| `Areas/基础设施` | `Areas/Infrastructure` |
| `Areas/个人健康档案` | `Areas/Personal Health Records` |
| `Areas/投资家庭事务` | `Areas/Investments and Family Affairs` |
| `Resources/书籍和出版物` | `Resources/Books and Publications` |
| `Resources/自媒体内容` | `Resources/Media Content` |
| `Personal Facts/个人履历.md` | `Personal Facts/Personal Facts.md` |

The remaining live notes and folders are renamed to English equivalents on the
same rule: translate the name, keep the location, keep the meaning.

## Procedure

1. **Back up.** The vault is not under version control. Take a full copy of the
   vault, or confirm a Time Machine or Obsidian file-recovery point, before any
   rename.
2. **Inventory.** Generate the exact note-and-folder rename list from the vault
   and keep it outside this repository. Private note titles must not be
   committed here.
3. **Rename inside Obsidian.** Use Obsidian's own rename (file explorer, or
   `Rename file`) rather than a shell `mv`. Obsidian rewrites `[[wikilinks]]`,
   heading links, and embeds to follow the new name. A scripted rename skips
   this step and silently breaks links.
4. **Rename folders bottom-up.** Rename child folders before their parents so
   intermediate paths stay valid throughout.
5. **Audit links.** Re-run the Chinese-link scan and confirm only `Archive/`
   targets remain, then open every remaining hit.
6. **Verify in Obsidian.** Open the vault index, check the graph view, and
   confirm each domain index note resolves.
7. **Update the repository.** Align the constitution, the feature
   specification, the README, and `templates/vault/AGENTS.md` with the names
   that actually landed.

## Open decisions

- `Areas/投资家庭事务` combines investments and family affairs in one folder.
  Keep it combined under one English name, or split it into two folders?
  Splitting is a structural change, not a rename, and needs its own approval.
- `Personal Facts/个人履历.md` would become `Personal Facts/Personal Facts.md`.
  Prefer a distinct note name, such as `Personal Facts/Profile.md`?
- Two Chinese-named folders sit under `Resources/Career/References/`. Rename
  them with the rest, or treat the career-reference tree as imported material?
- Should `Archive/` snapshots ever be renamed? This plan says no.

## Rollback

A rename is reversible one file at a time, but the link rewrites in step 3 are
not automatically undone by reversing the rename. The step-1 backup is the real
rollback path.

## Relationship to the repository

Until this migration runs, the vault's folder names are Chinese and the
repository's documentation names the English targets. That gap is deliberate and
temporary. The specs describe structure - top-level folders, the nested domain
layer, `Resources` for sources - and that structure is already accurate.
