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

## Release and DNS order

1. Request an ACM public certificate for `mcp.midu.com.au` in `ap-southeast-2`
   using DNS validation. The request is free. Keep the certificate ARN private
   to deployment configuration.
2. Add ACM's exact validation CNAME in Cloudflare. Set it to **DNS only** and
   disable CNAME flattening for that record. Wait until ACM reports `ISSUED`.
3. Add `https://mcp.midu.com.au/auth/callback` to the Google OAuth web client's
   authorized redirect URIs before changing the application base URL.
4. Set both `MCP_CUSTOM_DOMAIN_NAME=mcp.midu.com.au` and
   `MCP_CUSTOM_DOMAIN_CERTIFICATE_ARN=<issued Sydney ACM ARN>` in the trusted
   deployment configuration. The app stack creates the Regional API Gateway
   domain and maps its root to the existing `$default` stage. The MCP URL stays
   `/mcp`; OAuth callback stays `/auth/callback`.
5. Read `CustomDomainRecordTarget` from the application stack output. Create a
   Cloudflare CNAME with name `mcp`, target equal to that output, TTL Auto, and
   **DNS only**. Do not proxy this endpoint during first rollout; validate the
   direct API Gateway TLS and OAuth flow first.
6. Verify `https://mcp.midu.com.au/healthz` returns `200`, unauthenticated
   `POST /mcp` returns `401` with a Bearer challenge, and Google OAuth returns
   to the exact callback. Then update the MCP clients to
   `https://mcp.midu.com.au/mcp`.

Cloudflare DNS is intentionally not changed by the AWS release. DNS records
are domain-owner state; a scoped Cloudflare API token can be added to the
pipeline later if you want the pipeline to create and verify those records.
The API Gateway custom domain uses an AWS-managed certificate, so there is no
certificate private key for Cloudflare or CI to store.

## Rollback

Set both custom-domain inputs to their disabled defaults and release the
application stack. The API Gateway domain mapping is removed while the
generated `execute-api` endpoint remains available. Remove the `mcp` CNAME from
Cloudflare only after clients have moved back to the generated endpoint. Keep
the ACM validation CNAME if the certificate may be reused; ACM needs it for
automatic renewal.
