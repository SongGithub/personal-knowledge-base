# Cloud embedding model decision

**Status:** Owner approved private Markdown chunks and search queries through
Bedrock Sydney on 2026-10-19, selecting behaviour/bilingual-quality parity over
identical bge-m3 rankings. The initial hybrid release and synthetic OAuth proof
are recorded in [acceptance-results.md](acceptance-results.md). After the
expanded retrieval comparison, hybrid remains the cloud default with the
semantic-shortlist and explicit-identifier adjustments recorded below. The
default-winner gate passes on the latest live synthetic benchmark; deployment
is pending.

## Candidate

- Bedrock in `ap-southeast-2`, `cohere.embed-multilingual-v3`.
- Document chunks use `search_document`; search queries use `search_query`.
- 1,024 float32 dimensions, little-endian vector BLOBs, unit normalization,
  `paragraph-400-v1` chunks and contract ID
  `bedrock-cohere-multilingual-v3-f32-unit-paragraph-400-v1`. The smaller
  chunks keep long Chinese passages within the model input window; `END`
  truncation is a final provider-side safeguard.
- The model is pay per use. The first bulk build has one-time inference cost;
  ongoing changes embed only changed Markdown, while semantic searches embed
  each query. No permanent model instance is proposed.

AWS currently lists Cohere Embed Multilingual v3 as in-region in Sydney. Its
API distinguishes document and query inputs. Embed v4 is only globally routed
from Sydney as of this decision; that would allow processing outside Australia.
The local bge-m3 vectors are incompatible and must be regenerated in the
candidate model's space before activation.

The first live public synthetic run on 2026-10-19 measured vector top-1 14/14,
lexical top-1 12/14, and local-rule hybrid top-1 12/14 with top-3 13/14.
One cross-language query missed the hybrid top three. The cloud fusion now
promotes vector rank one to hybrid rank three when the local fusion would place
it lower. This keeps the best lexical/hybrid first result and protects semantic
recall. The revised live run measured lexical top-1 12/14, vector top-1 14/14,
hybrid top-1 12/14 and hybrid top-3 14/14, including cross-language top-3 2/2.
The initial trusted pipeline gate required hybrid top-1 at least 10/14,
top-3 at least 13/14 and both cross-language results in the top three.

The expanded `synthetic-bilingual-exact-v2` fixture adds four exact-identifier
queries to the prior 14 cases. A live 2026-10-19 rerun found lexical top-1
15/18, pure vector top-1 18/18 and hybrid top-1 16/18; vector and hybrid both
reached top-3 18/18 and cross-language top-3 2/2. Reciprocal-rank means were
0.8611, 1.0 and 0.9259 respectively. On this small fixture, pure vector is the
winner, so a model-configuration release cannot claim hybrid is best. The
comparison gate evaluates the deployed default against the strongest strategy
on the same cases and blocks a mismatched release. This is a fixture-level
decision, not evidence that vector search is universally better on the private
corpus.

The `synthetic-retrieval-stress-v3` fixture has 20 fully synthetic notes and 33
judged queries. It adds similar notes with different answers, paraphrases,
near-matching identifiers and six cross-language cases. Before the latest fix,
the live Bedrock Sydney run measured lexical top-1/top-3 at 22/33 and 26/33,
vector at 28/33 and 33/33, and hybrid at 25/33 and 31/33. Exact-ID top-1 was
7/7 lexical, 6/7 vector and 6/7 hybrid. Cross-language top-3 was 1/6 lexical,
6/6 vector and 5/6 hybrid. This exposed one bilingual fusion miss and blocked
the quality gate.

The fix makes the hybrid shortlist semantic-first for ordinary natural-language
queries: it preserves the vector top three and uses reciprocal-rank fusion for
the remaining candidates. Queries containing an explicit hyphenated note ID
start with lexical ranking, which correctly resolves an ID that vector search
confused with a related note. The benchmark now caches each query vector across
strategy comparisons so lexical, vector and hybrid are scored against the same
model output. A new live Bedrock Sydney run on 2026-10-19 passed both quality
and default-winner gates: lexical top-1/top-3 22/33 and 26/33; vector 28/33
and 33/33; hybrid 29/33 and 33/33. Exact-ID top-1 was 7/7 lexical, 6/7 vector
and 7/7 hybrid. Cross-language top-3 was 1/6 lexical, 6/6 vector and 6/6
hybrid. Hybrid MRR was 0.9343 versus vector 0.9192 and lexical 0.7273. The
in-memory synthetic index median query times were 0.5 ms lexical, 136.8 ms
vector and 135.3 ms hybrid; these exclude HTTP and cold starts.

A direct read-only check of the deployed 152-note, 2,457-chunk private index
used three generic queries. One cold snapshot load took 10.9 seconds; later
backend searches were roughly 0.6–0.8 seconds across strategies. A
deterministic 12-note sample selected by hashing eligible unique titles found
the expected note at rank one in 11/12 lexical, 10/12 vector and 11/12 hybrid;
all reached top three in 12/12. Only aggregate results were printed. Title
lookup favors lexical matching and cannot substitute for human-judged natural
language relevance. These measurements are direct backend calls, not deployed
OAuth/HTTP latency or availability tests.

**Recommendation:** retain `hybrid` as the cloud default. The semantic-first
shortlist and lexical identifier handling now pass the expanded floor and beat
vector on top-1, exact-ID accuracy and MRR, while tying vector on top-3 and
cross-language recall. Keep `lexical` and `vector` exposed for explicit
comparisons. This synthetic result does not establish relevance on the private
corpus; T047 remains open for an owner-judged 20–30-query set covering exact
lookup, English, Chinese, cross-language and ambiguous topics. The current
search always ranks a candidate for vector queries and has no relevance
threshold or abstention test; no-answer behavior needs its own design and
evaluation. The local OpenClaw MCP retains its existing hybrid contract.

The v3 minimum quality floor requires at least 30 cases, six cross-language
cases and seven exact-identifier cases; the configured default must reach at least
75% top-1, 90% top-3, all cross-language top-3, all but one exact top-1, and
remain within one top-1 result of lexical. The separate winner gate requires
the configured default to rank first by top-1, then top-3, cross-language
top-3, exact top-1 and mean reciprocal rank. The live synthetic comparison
runs on every trusted CodeBuild release; the winner condition is enforced when
the pinned commit changes the embedding, chunking, ranking or benchmark
configuration, or when the approved model ARN changes. An unavailable Git
comparison conservatively enables the winner condition.

The Bedrock Sydney account reported retention mode `inherit` on 2026-10-19.
This defers to the model default. AWS states that default mode may retain data
for abuse detection, while model providers do not receive it. The owner approved
Bedrock Sydney with this recorded boundary; no account-wide retention setting
was changed.

Sources: [model region availability](https://docs.aws.amazon.com/bedrock/latest/userguide/models-region-compatibility.html),
[Cohere Embed v3 request contract](https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-embed-v3.html),
[cross-region routing](https://docs.aws.amazon.com/bedrock/latest/userguide/cross-region-inference.html),
[Bedrock retention modes](https://docs.aws.amazon.com/bedrock/latest/userguide/data-retention.html).

## Approval and quality gate

The owner approved the proposed Cohere Embed Multilingual v3 in Bedrock Sydney
for private chunks and search queries on 2026-10-19. Record the effective
Bedrock retention mode before the first private call. The approval does not
authorize a globally routed model or a different provider.

Before activating the private index, compare lexical/vector/hybrid results
with the local MCP on representative English, Chinese and cross-language cases;
record top-1, top-3, citation correctness and latency. A different model may
have different rankings. If the owner requires identical model behaviour,
serve the same bge-m3 encoder in AWS and pin a different contract instead.
