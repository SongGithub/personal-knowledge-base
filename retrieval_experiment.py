#!/usr/bin/env python3
"""Read-only local KB retrieval experiment. Never sends text beyond loopback."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import statistics
import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import numpy as np

MODEL = "bge-m3-mlx-4bit"
AUTHORITY = {"canonical": 0, "verified": 1, "ordinary": 2, "archive": 3, "unverified": 4}
STOP = set("a an and are as at be did do for from how i in is it my of on or the to was were what when why with 的 了 吗 我 是 在 有 和".split())


def vault_default() -> Path:
    root = Path.home() / "Library/Mobile Documents/iCloud~md~obsidian/Documents"
    matches = [p for p in root.glob("KB") if p.is_dir()]
    if len(matches) != 1:
        raise SystemExit("Specify --vault; exactly one iCloud Obsidian KB vault was not found")
    return matches[0]


def private_default() -> Path:
    return Path.home() / "Library/Application Support/pkb-retrieval-experiment"


def tokens(text: str) -> list[str]:
    text = text.lower()
    words = re.findall(r"[a-z0-9]+|[\u3400-\u9fff]+", text)
    out = []
    for word in words:
        if re.fullmatch(r"[\u3400-\u9fff]+", word):
            out.extend(word[i:i + 2] for i in range(len(word) - 1))
            if len(word) == 1:
                out.append(word)
        elif word not in STOP:
            out.append(word)
    return out


def chunks(text: str, limit: int = 1500) -> list[str]:
    paragraphs = re.split(r"\n\s*\n", text.strip())
    result, current = [], ""
    for paragraph in paragraphs:
        # Long raw records are split without dropping content.
        pieces = [paragraph[i:i + limit] for i in range(0, len(paragraph), limit)] or [""]
        for piece in pieces:
            if current and len(current) + len(piece) + 2 > limit:
                result.append(current)
                current = ""
            current = f"{current}\n\n{piece}" if current else piece
    if current:
        result.append(current)
    return result or [""]


def authority(path: str, text: str, overrides: dict[str, str]) -> str:
    if path in overrides:
        tier = overrides[path]
        if tier not in AUTHORITY:
            raise ValueError(f"Unknown authority tier for {path}: {tier}")
        return tier
    low_path = path.lower()
    frontmatter = text.split("---", 2)[1].lower() if text.startswith("---\n") and text.count("---") >= 2 else ""
    if "_review/" in low_path or re.search(r"^status:\s*(draft|unverified|working-model|待核对)", frontmatter, re.M):
        return "unverified"
    if Path(path).name == "AGENTS.md" or re.search(r"^(status|authority):\s*(canonical|binding)", frontmatter, re.M):
        return "canonical"
    path_parts = {part.lower() for part in Path(path).parts}
    if path_parts & {"archive", "archives", "source archives", "source snapshots"}:
        return "archive"
    if re.search(r"^status:\s*(verified|confirmed)", frontmatter, re.M):
        return "verified"
    return "ordinary"


def endpoint(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Embedding endpoint must be plain HTTP on loopback")
    return url.rstrip("/")


def embed(texts: list[str], url: str, model: str) -> np.ndarray:
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)
    request = Request(endpoint(url) + "/embeddings", data=json.dumps({"model": model, "input": texts}).encode(), headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=180) as response:
        payload = json.load(response)
    items = sorted(payload["data"], key=lambda item: item["index"])
    if len(items) != len(texts):
        raise RuntimeError("Embedding response count mismatch")
    vectors = np.asarray([item["embedding"] for item in items], dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1)
    if not np.isfinite(vectors).all() or (norms == 0).any():
        raise RuntimeError("Invalid embedding vector")
    return vectors / norms[:, None]


def database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE IF NOT EXISTS notes(path TEXT PRIMARY KEY, tier TEXT NOT NULL, sha256 TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS chunks(path TEXT NOT NULL, ordinal INTEGER NOT NULL, text TEXT NOT NULL, vector BLOB, PRIMARY KEY(path, ordinal))")
    db.execute("CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    return db


def source_snapshot(vault: Path) -> tuple[list[tuple[str, str, str]], str]:
    root = vault.resolve()
    paths = []
    for path in vault.rglob("*.md"):
        if ".obsidian" in path.parts or path.is_symlink() or not path.is_file():
            continue
        try:
            path.resolve().relative_to(root)
        except ValueError:
            continue
        paths.append(path)
    paths.sort()
    manifest = []
    for path in paths:
        raw = path.read_bytes()
        manifest.append((path.relative_to(vault).as_posix(), hashlib.sha256(raw).hexdigest(), raw.decode("utf-8-sig")))
    source_hash = hashlib.sha256(json.dumps([(path, digest) for path, digest, _ in manifest], ensure_ascii=False).encode()).hexdigest()
    return manifest, source_hash


def build(vault: Path, db: sqlite3.Connection, url: str, model: str, overrides: dict[str, str], batch_size: int = 16) -> dict:
    manifest, source_hash = source_snapshot(vault)
    override_hash = hashlib.sha256(json.dumps(overrides, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    wanted = {"source_hash": source_hash, "model": model, "override_hash": override_hash, "chunker": "paragraph-1500-v1", "authority_rules": "v3"}
    current = dict(db.execute("SELECT key,value FROM metadata"))
    if current == wanted and db.execute("SELECT COUNT(*) FROM chunks WHERE vector IS NULL").fetchone()[0] == 0:
        return {"notes": len(manifest), "chunks": db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0], "rebuilt": False, "source_hash": source_hash}
    if all(current.get(key) == wanted[key] for key in ("source_hash", "model", "chunker")) and db.execute("SELECT COUNT(*) FROM chunks WHERE vector IS NULL").fetchone()[0] == 0:
        with db:
            db.executemany("UPDATE notes SET tier=? WHERE path=?", [(authority(path, content, overrides), path) for path, _, content in manifest])
            db.execute("DELETE FROM metadata")
            db.executemany("INSERT INTO metadata VALUES(?,?)", wanted.items())
        return {"notes": len(manifest), "chunks": db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0], "rebuilt": False, "authority_refreshed": True, "source_hash": source_hash}
    with db:
        db.execute("DELETE FROM chunks")
        db.execute("DELETE FROM notes")
        db.execute("DELETE FROM metadata")
        for path, digest, content in manifest:
            db.execute("INSERT INTO notes VALUES(?,?,?)", (path, authority(path, content, overrides), digest))
            for i, part in enumerate(chunks(content)):
                db.execute("INSERT INTO chunks VALUES(?,?,?,NULL)", (path, i, part))
    rows = list(db.execute("SELECT path,ordinal,text FROM chunks ORDER BY path,ordinal"))
    for start in range(0, len(rows), batch_size):
        batch = rows[start:start + batch_size]
        vectors = embed([row[2] for row in batch], url, model)
        with db:
            db.executemany("UPDATE chunks SET vector=? WHERE path=? AND ordinal=?", [(vector.tobytes(), row[0], row[1]) for row, vector in zip(batch, vectors)])
        print(f"embedded {min(start + batch_size, len(rows))}/{len(rows)}", flush=True)
    with db:
        db.executemany("INSERT INTO metadata VALUES(?,?)", wanted.items())
    return {"notes": len(manifest), "chunks": len(rows), "rebuilt": True, "source_hash": source_hash}


class Search:
    def __init__(self, db: sqlite3.Connection, url: str, model: str):
        self.url, self.model = url, model
        self.rows = list(db.execute("SELECT c.path,c.ordinal,c.text,c.vector,n.tier FROM chunks c JOIN notes n USING(path) ORDER BY c.path,c.ordinal"))
        if any(row[3] is None for row in self.rows):
            raise RuntimeError("Index has missing vectors; rebuild it")
        self.tiers = {row[0]: row[4] for row in self.rows}
        self.lex = [Counter(tokens(row[2] + " " + Path(row[0]).stem * 2)) for row in self.rows]
        self.lengths = [sum(freq.values()) for freq in self.lex]
        self.avglen = statistics.mean(self.lengths) if self.lengths else 1
        self.df = Counter(t for terms in self.lex for t in terms)
        self.vectors = np.stack([np.frombuffer(row[3], dtype=np.float32) for row in self.rows])

    def lexical(self, query: str) -> list[str]:
        q = Counter(tokens(query))
        scores = defaultdict(float)
        n = len(self.rows)
        for (path, _, _, _, _), terms, length in zip(self.rows, self.lex, self.lengths):
            score = 0.0
            for term, qfreq in q.items():
                tf = terms.get(term, 0)
                if tf:
                    idf = math.log(1 + (n - self.df[term] + .5) / (self.df[term] + .5))
                    score += qfreq * idf * tf * 2.2 / (tf + 1.2 * (.25 + .75 * length / self.avglen))
            scores[path] = max(scores[path], score)
        return [p for p, score in sorted(scores.items(), key=lambda x: (-x[1], x[0])) if score > 0]

    def vector(self, query: str) -> list[str]:
        ranking, _ = self.vector_with_scores(query)
        return ranking

    def vector_with_scores(self, query: str) -> tuple[list[str], np.ndarray]:
        q = embed([query], self.url, self.model)[0]
        similarities = self.vectors @ q
        scores = defaultdict(lambda: -1.0)
        for row, score in zip(self.rows, similarities):
            scores[row[0]] = max(scores[row[0]], float(score))
        ranking = [p for p, _ in sorted(scores.items(), key=lambda x: (-x[1], x[0]))]
        return ranking, similarities

    def hybrid(self, lex: list[str], vec: list[str]) -> list[str]:
        # Vector-weighted RRF; authority changes ordering only for near ties.
        # This prevents an unrelated canonical note from eclipsing a relevant source.
        scores = defaultdict(float)
        for ranking, weight in ((lex[:30], .25), (vec[:30], .75)):
            for rank, path in enumerate(ranking, 1):
                scores[path] += weight / (60 + rank)
        fused = sorted(scores, key=lambda p: (-scores[p], p))
        if not fused:
            return []
        cutoff = scores[fused[0]] * .98
        eligible = [p for p in fused if scores[p] >= cutoff]
        ineligible = [p for p in fused if scores[p] < cutoff]
        eligible.sort(key=lambda p: (AUTHORITY[self.tiers[p]], -scores[p], p))
        return eligible + ineligible


def ndcg_variance(rankings: list[list[str]]) -> float:
    if len(rankings) < 2:
        return 0.0
    universe = set().union(*(set(r[:5]) for r in rankings))
    if not universe:
        return 0.0
    values = []
    for note in universe:
        positions = [r.index(note) + 1 if note in r[:5] else 6 for r in rankings]
        values.append(statistics.pvariance(positions))
    return statistics.mean(values)


def run_benchmark(search: Search, cases: list[dict], repeats: int) -> dict:
    results = {strategy: [] for strategy in ("lexical", "vector", "hybrid")}
    for case in cases:
        for query in case["paraphrases"]:
            for _ in range(repeats):
                start = time.perf_counter()
                lex = search.lexical(query)
                lex_ms = (time.perf_counter() - start) * 1000
                start = time.perf_counter()
                vec = search.vector(query)
                vec_ms = (time.perf_counter() - start) * 1000
                start = time.perf_counter()
                hyb = search.hybrid(lex, vec)
                hyb_ms = (time.perf_counter() - start) * 1000
                for name, ranking, latency in (("lexical", lex, lex_ms), ("vector", vec, vec_ms), ("hybrid", hyb, lex_ms + vec_ms + hyb_ms)):
                    results[name].append({"case": case["id"], "query": query, "expected": case["expected_paths"], "canonical_expected": case.get("canonical_expected", False), "top5": ranking[:5], "tiers": [search.tiers[p] for p in ranking[:5]], "latency_ms": round(latency, 3)})
    summary = {}
    for name, rows in results.items():
        by_query = defaultdict(list)
        by_case = defaultdict(list)
        for row in rows:
            by_query[(row["case"], row["query"])].append(row["top5"])
            by_case[row["case"]].append(row)
        expected_rows = [r for r in rows if r["expected"]]
        canonical_rows = [r for r in rows if r["canonical_expected"]]
        summary[name] = {
            "top1_accuracy": mean([bool(r["top5"] and r["top5"][0] in r["expected"]) for r in expected_rows]),
            "top3_recall": mean([bool(set(r["top5"][:3]) & set(r["expected"])) for r in expected_rows]),
            "top5_recall": mean([bool(set(r["top5"]) & set(r["expected"])) for r in expected_rows]),
            "same_top1_rate": mean([len({tuple(x[:1]) for x in runs}) == 1 for runs in by_query.values()]),
            "ranking_variance": mean([ndcg_variance(runs) for runs in by_query.values()]),
            "paraphrase_agreement_rate": mean([len({r["top5"][0] if r["top5"] else None for r in case_rows}) == 1 for case_rows in by_case.values()]),
            "canonical_top1_rate": mean([bool(r["top5"] and r["tiers"][0] == "canonical") for r in canonical_rows]),
            "wrong_archive_override_rate": mean([bool(r["top5"] and r["tiers"][0] == "archive" and r["top5"][0] not in r["expected"]) for r in canonical_rows]),
            "unverified_draft_top1_rate": mean([bool(r["top5"] and r["tiers"][0] == "unverified") for r in rows]),
            "latency_ms_median": round(statistics.median(r["latency_ms"] for r in rows), 3),
            "latency_ms_p95": round(sorted(r["latency_ms"] for r in rows)[math.ceil(.95 * len(rows)) - 1], 3),
        }
    return {"summary": summary, "results": results}


def mean(items: list) -> float | None:
    return round(sum(items) / len(items), 4) if items else None


def markdown_report(report: dict) -> str:
    summary, results = report["summary"], report["results"]
    metrics = ("top1_accuracy", "top3_recall", "top5_recall", "same_top1_rate", "ranking_variance", "paraphrase_agreement_rate", "canonical_top1_rate", "wrong_archive_override_rate", "unverified_draft_top1_rate", "latency_ms_median", "latency_ms_p95")
    lines = ["# Private retrieval benchmark", "", f"Model: `{report['provenance']['model']}`; model SHA-256: `{report['provenance'].get('model_sha256')}`; notes: {report['provenance']['notes']}; chunks: {report['provenance']['chunks']}; repeats: {report['provenance']['repeats']}.", "", "| Metric | Lexical | Vector | Hybrid |", "|---|---:|---:|---:|"]
    for metric in metrics:
        lines.append(f"| {metric} | {summary['lexical'][metric]} | {summary['vector'][metric]} | {summary['hybrid'][metric]} |")
    lines += ["", "## Per-query top 1", "", "✓ means the top note matches an expected path. Full top five and timings are in `report.json`.", "", "| Case | Paraphrase | Lexical | Vector | Hybrid |", "|---|---|---|---|---|"]
    lexical, vector, hybrid = (results[name] for name in ("lexical", "vector", "hybrid"))
    for l, v, h in zip(lexical[::report['provenance']['repeats']], vector[::report['provenance']['repeats']], hybrid[::report['provenance']['repeats']]):
        def cell(row):
            if not row["top5"]:
                return "—"
            marker = "✓" if row["top5"][0] in row["expected"] else "✗"
            return f"{marker} {Path(row['top5'][0]).name} ({row['tiers'][0]})".replace("|", "\\|")
        lines.append(f"| {l['case']} | {l['query'].replace('|', '\\|')} | {cell(l)} | {cell(v)} | {cell(h)} |")
    lines += ["", "## Unstable identical queries", ""]
    unstable = []
    for name, rows in results.items():
        grouped = defaultdict(set)
        for row in rows:
            grouped[(row["case"], row["query"])].add(tuple(row["top5"]))
        unstable.extend(f"- {name}: {case}: {query}" for (case, query), rankings in grouped.items() if len(rankings) > 1)
    lines += unstable or ["None within this process. Compare separate process runs as well."]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["index", "benchmark", "search"])
    parser.add_argument("--vault", type=Path)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--authority", type=Path)
    parser.add_argument("--query")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 2:
        parser.error("--repeats must be at least 2")
    vault = (args.vault or vault_default()).expanduser().resolve()
    data_dir = (args.data_dir or private_default()).expanduser().resolve()
    if data_dir == vault or vault in data_dir.parents:
        parser.error("Data directory must be outside the vault")
    repository = Path(__file__).resolve().parent
    if data_dir == repository or repository in data_dir.parents:
        parser.error("Data directory must be outside the repository")
    endpoint(args.endpoint)
    overrides = json.loads(args.authority.read_text()) if args.authority else {}
    db = database(data_dir / "index.sqlite")
    info = build(vault, db, args.endpoint, args.model, overrides)
    print(json.dumps(info))
    if args.command == "index":
        return
    search = Search(db, args.endpoint, args.model)
    if args.command == "search":
        if not args.query:
            parser.error("search requires --query")
        lex, vec = search.lexical(args.query), search.vector(args.query)
        print(json.dumps({name: [{"path": p, "tier": search.tiers[p]} for p in ranking[:5]] for name, ranking in (("lexical", lex), ("vector", vec), ("hybrid", search.hybrid(lex, vec)))}, ensure_ascii=False, indent=2))
        return
    if not args.cases:
        parser.error("benchmark requires --cases")
    cases = json.loads(args.cases.read_text())
    for case in cases:
        if not case.get("id") or not case.get("paraphrases") or not case.get("expected_paths"):
            parser.error("Each case requires id, paraphrases and expected_paths")
        for path in case["expected_paths"]:
            if path not in search.tiers:
                parser.error(f"Expected note missing from indexed vault: {path}")
    report = run_benchmark(search, cases, args.repeats)
    model_file = Path.home() / ".omlx/models" / args.model / "model.safetensors"
    model_digest = None
    if model_file.is_file():
        with model_file.open("rb") as handle:
            model_digest = hashlib.file_digest(handle, "sha256").hexdigest()
    report["provenance"] = {**info, "model": args.model, "model_sha256": model_digest, "repeats": args.repeats, "cases": len(cases), "timestamp_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()}
    target = data_dir / "report.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    (data_dir / "report.md").write_text(markdown_report(report))
    print(json.dumps({"report": str(target), "summary": report["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
