# Cloud embedding model decision

**Status:** Owner approved private Markdown chunks and search queries through
Bedrock Sydney on 2026-10-19, selecting behaviour/bilingual-quality parity over
identical bge-m3 rankings. Deployment and acceptance remain to be proven.

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
The trusted pipeline gate requires hybrid top-1 at least 10/14, hybrid top-3 at
least 13/14, both cross-language results in top three, and hybrid top-1 within
one result of lexical. Re-run this public synthetic benchmark before each model
deployment; record the result without private data.

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
