# MCP custom domain

The service URL is `https://mcp.midu.com.au/mcp`. The HTTP API remains
in `ap-southeast-2`, with a Regional API Gateway custom domain and TLS 1.2.
Cloudflare remains the authoritative DNS provider; the root `midu.com.au` record
is not involved.

## Activation evidence

On 20 October 2026, the existing CodeBuild pipeline deployed the custom domain
and mapping from merged commit `68ced971e2d67d64b9fcfb1e6bbcdf77b27a5f38`.
It reads the DNS token's JSON key from the exact AWS Secrets Manager reference.
The Google web client's custom callback is configured alongside the existing
raw and loopback callbacks. No grants were widened by deployment.

Independent checks confirm a DNS-only CNAME, a valid certificate for the
hostname, health HTTP 200, anonymous and invalid-token HTTP 401, and custom-origin
issuer, protected-resource and OAuth endpoint metadata. The raw endpoint still
enforces authentication. The first build's final HTTPS check timed out during
DNS propagation; the deployment itself reached UPDATE_COMPLETE. A pinned retry
then completed successfully, including the pipeline's DNS and HTTPS checks.
Fresh authenticated acceptance remains tracked in
[UPS-58](https://jin-family.atlassian.net/browse/UPS-58).

Clients should use the service URL above and reconnect through Google OAuth.
Tokens belong to their issuer; an old-origin token is not proof of custom-origin
access. Reusing a registered client identity preserves its existing backend grant;
a client that registers a new identity needs separate owner approval.

## Certificate choice

Use a non-exportable public certificate issued by AWS Certificate Manager
(ACM), validated through Cloudflare DNS. ACM certificates used by API Gateway
are free and ACM renews them while the DNS validation CNAME stays in place.
Let's Encrypt is also free, but API Gateway needs its certificate imported into
ACM, and imported certificates do not receive ACM managed renewal. That would
add a renewal job, secret private-key handling, and a deployment on every
renewal without lowering the certificate cost. [ACM pricing](https://aws.amazon.com/certificate-manager/pricing/)
and [API Gateway certificate requirements](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-regional-api-custom-domain-create.html).

## One-time setup

1. Create a Cloudflare API token restricted to the `midu.com.au` zone, granting
   `Zone:Read` and `DNS:Edit`. Do not use the global API key. The pipeline only
   writes `mcp.midu.com.au` and ACM validation records beneath it, always with
   Cloudflare proxying disabled.
2. For the GitHub Actions deployment path, store the token as the repository
   Actions secret `CLOUDFLARE_API_TOKEN_DNS`; the deploy job passes it to the
   app without printing it. For the selected AWS-native CodeBuild path, GitHub
   secrets are not readable by CodeBuild. Store a copy in AWS Secrets Manager
   in `ap-southeast-2`, for example `pkb/dev/cloudflare-dns`, using
   `python3 tools/store_cloudflare_dns_token.py`; then pass its ARN through
   `--cloudflare-dns-token-secret-arn`. Store the value as the JSON key
   `CLOUDFLARE_API_TOKEN_DNS`; the CodeBuild environment selects that key.
   CodeBuild receives
   `secretsmanager:GetSecretValue` on that exact ARN. The token itself is never
   a CloudFormation parameter.
3. Add `https://mcp.midu.com.au/auth/callback` to the Google OAuth web client's
   authorized redirect URIs before release.
4. Enable the hostname by passing `--custom-domain-name mcp.midu.com.au`,
   `--custom-domain-certificate-arn <Sydney ACM ARN>`, and
   `--cloudflare-dns-token-secret-arn <Secrets Manager ARN>` to the bootstrap
   command. The certificate ARN must be in `ap-southeast-2`.

## Release and DNS order

On a configured release, CodeBuild reads the Cloudflare token from Secrets
Manager, creates the ACM DNS validation CNAME, waits for ACM to issue the
certificate, deploys the Regional API Gateway custom domain and `$default`
mapping, then creates/updates the service CNAME to the API Gateway target. Both
records are DNS-only. It finishes by checking the custom health endpoint and
confirming unauthenticated MCP requests receive a Bearer challenge. Conflicting
pre-existing records fail closed; the pipeline will not overwrite them.

After the first successful deployment, update the MCP clients to
`https://mcp.midu.com.au/mcp` and verify the Google OAuth callback.

## Deployment permission checks

On 20 October 2026, UPS-57 verified actual domain and mapping creation with the
intended CloudFormation role after correcting the IAM conditions and tagging
path below. No organisation policy change was required. DNS, runtime URL and
OAuth activation remain in [UPS-58](https://jin-family.atlassian.net/browse/UPS-58).

API Gateway v2 supplies `apigateway:Request/EndpointType` and
`apigateway:Request/SecurityPolicy` as arrays. Both bootstrap variants use
`ForAllValues:StringEquals` for the Regional/TLS 1.2 restrictions, with `Null`
checks that reject missing values. Project and environment tags remain scalar
`StringEquals` conditions. Simulating these keys as scalar strings can produce
a false positive even when live creation fails. See the
[API Gateway v2 condition types](https://docs.aws.amazon.com/service-authorization/latest/reference/list_apigatewayv2.html)
and [IAM set operators](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_condition-single-vs-multi-valued-context-keys.html).

The tagging resource list also includes the exact URL-encoded domain ARN used
by API Gateway's `/tags/` endpoint. Both encoded and unencoded paths remain
restricted to `mcp.midu.com.au`; no general domain or tagging wildcard is needed.

For permission acceptance, use the CloudFormation execution role to create the
intended domain and `$default` API mapping in a temporary stack, without DNS or
runtime URL changes. Check the actual domain and mapping, then delete that
temporary stack before normal application deployment takes ownership. Keep
private stack handles and raw AWS evidence outside Git. A simulator result or
an issued ACM certificate alone does not establish live deployment permission.

The API Gateway custom domain uses an AWS-managed certificate, so there is no
certificate private key for Cloudflare or CI to store.

## Rollback

Run the bootstrap helper with `--disable-custom-domain`, then release the
application stack. This disables the hostname, certificate and token reference
together. The API Gateway domain mapping is removed while
the generated `execute-api` endpoint remains available. Remove the `mcp` CNAME
from Cloudflare only after clients have moved back to the generated endpoint.
Keep the ACM validation CNAME if the certificate may be reused; ACM needs it
for automatic renewal.
