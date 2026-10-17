# Research and decision record

**Date**: 2026-10-17. Decisions below are proposed design; owner requirements are
identified in [spec.md](spec.md). Sources are public; no private notes, identities,
credentials or corpus measurements are included. Acceptance and cost measurements
remain future implementation work.

## 1. Occasional compute with regional resilience

**Decision**: Prefer ordinary on-demand Lambda Event Functions for the existing
Python core, fronted by HTTP API, with no provisioned concurrency.

**Rationale**: Lambda manages execution across availability zones and bills
requests/duration. The owner accepts cold starts, removing the need to pay for
warm replicas. This provides regional resilience, not region-outage immunity or
an end-to-end availability guarantee.

**Alternatives considered**: Azure Container Apps Consumption fits portable HTTP
containers and scales to zero; its zone-distribution guidance recommends at least
two minimum replicas. Azure Functions Flex also scales to zero normally, but
zone-redundant Flex requires at least two always-ready instances. These tradeoffs
make Lambda the stronger proposed fit for this owner, not a universal cheapest
platform claim. Newly launched Lambda Web Functions currently support Node.js;
they do not remove the Python migration work.

Sources: [Lambda resilience](https://docs.aws.amazon.com/lambda/latest/dg/security-resilience.html),
[Lambda pricing](https://aws.amazon.com/lambda/pricing/),
[HTTP API pricing](https://aws.amazon.com/api-gateway/pricing/),
[Container Apps reliability](https://learn.microsoft.com/en-us/azure/reliability/reliability-container-apps),
[Container Apps pricing](https://azure.microsoft.com/en-us/pricing/details/container-apps/),
[Functions reliability](https://learn.microsoft.com/en-us/azure/reliability/reliability-functions),
[Lambda Web Functions](https://docs.aws.amazon.com/lambda/latest/dg/web-functions.html).

## 2. Authoritative private Markdown in S3

**Decision**: Plan an authority cutover to S3 after a migration rehearsal, retaining
the existing directory/path semantics as object keys and export structure.

**Rationale**: The owner has no Obsidian viewing/editing dependency and accepts
cloud storage migration. S3 offers direct service APIs, strong read-after-write
consistency, per-object versioning and conditional writes. This removes the need
for a home device to proxy canonical writes after cutover. S3 does not supply
multi-object transactions or semantic retrieval; application reconciliation is
still required.

**Alternatives considered**: Existing iCloud-backed local access retains a Mac
dependency in this implementation; the NAS-only replica cannot be an independent
canonical writer under feature 005. MCP itself does not mandate S3 or migration.

Sources: [S3 consistency/versioning](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html),
[conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html),
[Obsidian storage model](https://obsidian.md/help/data-storage).

## 3. Embedding compute and index persistence are separate

**Decision**: Keep a rebuildable SQLite snapshot initially; evaluate approved
on-demand cloud embeddings for the production query and document paths.

**Rationale**: Inspection of `retrieval_experiment.py` shows `embed()` calls a
loopback embeddings endpoint, while `database()`, `_embed_rows()` and `build()`
store chunks/vectors/metadata in `index.sqlite`. `Search.vector_with_scores()`
also calls the model for each question. The model server is not the KB database.
The builder already reuses unchanged vectors. `kb_mcp_server.py` currently gates
fetch on index freshness; the cloud design must separate these concerns.

The current oMLX runtime targets Apple Silicon/macOS; it cannot be assumed to run
as the same image in a standard Linux Lambda deployment. A local worker can read
S3 and upload an index without iCloud, but local query embedding still prevents
independent semantic serving. A cloud model change requires compatibility review,
usually document re-embedding and bilingual quality comparison. Provider/model
selection and consent precede private calls; no existing private vectors may be
silently mixed with a new embedding space.

**Alternatives considered**: Local oMLX for optional batch processing; a Linux
self-hosted encoder if measured operating cost justifies it; a managed vector
service if the snapshot ceases to fit memory/time limits. Do not introduce a
continuously running model/vector cluster for occasional traffic by default.

Sources: [oMLX requirements and embedding support](https://github.com/jundot/omlx/blob/main/README.md),
[Bedrock embeddings](https://docs.aws.amazon.com/bedrock/latest/userguide/titan-embedding-models.html),
[Bedrock pricing](https://aws.amazon.com/bedrock/pricing/).

## 4. Google identity, application grants and AWS roles

**Decision**: Google identifies the owner; a maintained OAuth authorization
component issues separate MCP client grants; the KB backend enforces effective
permissions. AWS roles govern deployment and service-to-service access only.

**Rationale**: Google `sub` provides a stable owner identity. Google sign-in alone
does not grant read/write paths, and Google tokens are not pass-through MCP
resource tokens. Auth state must survive Lambda recycling. FastMCP's Google
provider is a candidate; its persistent encrypted state and signing keys require
production integration and actual client interoperability validation.

**Alternatives considered**: Placing all document policy in the IdP; accepting any
successful Google login; putting grants in a disposable SQLite index; handing AI
clients AWS/SSH credentials. These do not meet the defined boundary.

Sources: [Google OIDC](https://developers.google.com/identity/openid-connect/openid-connect),
[MCP authorization](https://modelcontextprotocol.io/specification/latest/basic/authorization),
[MCP security practices](https://modelcontextprotocol.io/specification/latest/basic/security_best_practices),
[FastMCP Google integration](https://gofastmcp.com/integrations/google).

## 5. Temporary deployment credentials and bootstrap

**Decision**: Local CLI profile with temporary credentials and a bounded deployer
role; Identity Center SSO if available, otherwise supported browser-based CLI
login with an IAM/federated console identity. Use GitHub Actions OIDC for routine
infrastructure releases after a one-time CloudFormation trust bootstrap.

**Rationale**: No pasted/stored long-lived AWS key is needed. A role ARN alone
does not provide authentication. Initial role/trust creation requires an existing
authorized administrator. Separate CloudFormation and execution roles; restrict
PassRole, stack operations and service-role permissions to avoid privilege
expansion. CloudFormation can reuse a stack's attached service role for callers
who can operate that stack, so PassRole constraints alone are insufficient.

**Original documentation observation**: The discovered AWS executable failed
because its Python interpreter path was missing; that stage made no AWS calls.
The later read-only [permission audit](permission-verification.md) authenticated
successfully using a private helper and validated both authored templates.
Representative deployment checks passed, but organisation controls deny OIDC
provider operations. An authorised administrator must confirm an approved
provider/setup. No infrastructure or policies have been changed. Repair/install
CLI v2 before following the bootstrap access guide.

Sources and setup details: [deployment-access.md](deployment-access.md).

## Decision gates for implementation

- Confirm account/region, exact trusted deployer and IAM bootstrap, and regional cost.
- Validate a maintained OAuth/broker storage integration and actual client versions.
- Measure corpus/snapshot size and select an embedding model after quality/cost
  comparison; obtain private-content model approval before use.
- Configure permitted capture/proposal destinations and human approval access.
- Rehearse migration, export/restore and post-cutover write reconciliation.

These are explicit implementation/deployment gates, not missing facts hidden as
completed research or claims of production readiness.
