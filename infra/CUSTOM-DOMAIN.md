# MCP custom domain

The intended service URL is `https://mcp.midu.com.au/mcp`. The HTTP API remains
in `ap-southeast-2`, with a Regional API Gateway custom domain and TLS 1.2.
Cloudflare remains the authoritative DNS provider; the root `midu.com.au` record
is not involved.

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
2. Store that token as an AWS Secrets Manager secret in `ap-southeast-2`, for
   example `pkb/dev/cloudflare-dns`. The repository helper prompts without
   echoing it: `python3 tools/store_cloudflare_dns_token.py`. Give the pipeline the secret ARN through
   `--cloudflare-dns-token-secret-arn`; the CodeBuild role receives only
   `secretsmanager:GetSecretValue` on that exact ARN. The token itself is never
   a CloudFormation parameter or repository secret.
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
