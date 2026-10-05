# Personal Knowledge Base

> 知识库的价值=知识的密度X调用的频率X验证的深度

A private, portable wiki workflow for turning sources into reviewable knowledge
pages and answering questions with evidence. The first release targets one user,
an Obsidian vault, a small local CLI, and OpenClaw.

This repository contains the project specification and, later, code and
templates. Private sources and generated wiki pages belong in the user's vault,
outside Git.

## Current status

Specification draft. No application code or private vault content has been
added to this repository. The target `KB` layout uses the owner's seven
top-level categories: 基础设施, 个人履历, 投资, 书籍和出版物, 自媒体内容,
家庭事务, and 个人健康档案. The vault migration is awaiting review. The
specification places subject-specific sources and projects under their owning
category, with shared governance and navigation under `基础设施`.
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
