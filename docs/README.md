# File Manager Service Docs

This directory contains the working specification for the ArnaTech file manager service.

The service is intended to:

- accept uploads from multiple internal services
- return a stable file URL that can be stored elsewhere
- use S3-compatible object storage with presigned access
- support Google Drive or Nextcloud style browsing and file management
- enforce user and organization aware permissions using the existing SSO JWT

## Read This First

If you are a human product or engineering stakeholder:

1. Start with [PRD.md](./PRD.md)
2. Continue with [ARCHITECTURE.md](./ARCHITECTURE.md)
3. Use [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) for delivery planning

If you are an engineer or AI agent implementing the service:

1. Start with [ARCHITECTURE.md](./ARCHITECTURE.md)
2. Read [DATA_MODEL.md](./DATA_MODEL.md)
3. Read [API_SPEC.md](./API_SPEC.md)
4. Use [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) as the build sequence

## Core Design Decisions

- Canonical file identity is an immutable UUID URL: `https://storage.arnatech.id/<uuid>`
- File placement inside folders is mutable metadata and does not affect the canonical URL
- Object storage is private by default
- Clients upload directly to S3-compatible storage using presigned multipart upload URLs
- The service stores metadata, access control, shares, folders, and upload state
- Authentication uses bearer JWTs issued by the existing SSO and verified locally using `public.pem`

## Local Inputs Used For This Spec

- SSO contract: [`/sso-api.json`](/c:/Users/ThinkPad/Documents/Arnatech/file_manager/sso-api.json)
- JWT verification key: [`/public.pem`](/c:/Users/ThinkPad/Documents/Arnatech/file_manager/public.pem)

## Suggested Repository Layout

```text
file_manager/
  manage.py
  requirements.txt
  .env.example
  config/
  apps/
    authn/
    files/
    folders/
    sharing/
    access/
    uploads/
    audit/
  docs/
  frontend/
  infra/
```

## Status

This documentation is written as a v1 build spec. It intentionally prefers a narrow, shippable scope over a fully generalized collaboration platform.
