# Personal Knowledge Base

> The value of a knowledge base = knowledge density x retrieval frequency x
> depth of verification

A private, portable wiki workflow for turning sources into reviewable knowledge
pages and answering questions with evidence. The first release targets one user,
an Obsidian vault, a small local CLI, and assistant clients such as OpenClaw and
Codex.

This repository contains the project specification and, later, code and
templates. Private sources and generated wiki pages belong in the user's vault,
outside Git.

## Current status

The local retrieval experiment and read-only local MCP service are implemented.
See the [shared retrieval spec](specs/003-shared-kb-retrieval/spec.md) and
[OpenClaw connection guide](docs/openclaw-kb-connection.md) to configure
OpenClaw. ChatGPT-specific connectivity remains a separate, unimplemented
adapter. The `KB` vault keeps its top-level folders (`Ideas`, `Projects`,
`Areas`, `Resources`, `Archive`, `Wiki`, `Personal Facts`) and records the
owner's domain categories as index notes nested inside them, with sources in
`Resources`. The vault folders are still Chinese; a link-safe migration to
English names is planned in
[vault-english-migration.md](docs/vault-english-migration.md) and is not yet
approved. A public template for the vault's AI instructions is in
[`templates/vault/AGENTS.md`](templates/vault/AGENTS.md).

Review the [constitution](.specify/memory/constitution.md) and
[MVP feature specification](specs/001-personal-wiki-workflow/spec.md) before
creating the implementation plan or tasks.

## Development workflow

The repository includes GitHub Spec Kit with Codex integration. Work proceeds
through constitution, specification, plan, tasks, and implementation, with
review at each boundary. Keep synthetic examples in the repo and private data
in the vault.
# Local retrieval quality experiment

The experimental [retrieval CLI](retrieval_experiment.py) compares deterministic
lexical, local MLX vector, and authority-aware hybrid retrieval. It reads an
Obsidian `KB` vault without changing Markdown. Its SQLite index is disposable.
See [the experiment specification](specs/002-retrieval-quality-experiment/spec.md)
for the evaluation boundary and decision rule.

Install `numpy` from [requirements.txt](requirements.txt), run a local oMLX
server with a multilingual embedding model, then run:

```sh
python3 retrieval_experiment.py index --model bge-m3-mlx-4bit
python3 retrieval_experiment.py benchmark --cases /path/outside/repo/private-cases.json --repeats 3
```

The vault is discovered under the current user's iCloud Obsidian container;
`--vault` overrides discovery. The index/report default to the current user's
`Library/Application Support/pkb-retrieval-experiment`; `--data-dir` overrides
that location but must remain outside the repository and vault. `--authority`
accepts a private JSON map from relative note paths to `canonical`, `verified`,
`ordinary`, `archive`, or `unverified`. The CLI refuses a non-loopback embedding
endpoint. The public [synthetic case](examples/synthetic-cases.json) shows the
benchmark format; real cases and reports belong outside Git.
