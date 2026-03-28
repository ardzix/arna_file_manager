# Architecture Specification

## Recommended Stack

### Backend

- Python 3.12+
- Django
- Django REST Framework
- PostgreSQL
- Redis
- Celery
- boto3
- PyJWT or python-jose
- drf-spectacular

### Frontend

- Next.js
- TypeScript
- Tailwind CSS

### Infra

- S3-compatible object storage
- Nginx or Traefik
- Docker
- MinIO for local development if needed

## Why This Stack

- Django and DRF are a strong fit for relational metadata, access rules, folders, and audit logs
- The SSO contract in [`/sso-api.json`](/c:/Users/ThinkPad/Documents/Arnatech/file_manager/sso-api.json) already resembles a DRF style API, which reduces friction across services
- boto3 provides strong support for presigned multipart upload workflows
- PostgreSQL is the right source of truth for ownership, folders, visibility, and sharing logic

## High-Level System Design

The service is a metadata and authorization layer in front of object storage.

Object bytes:

- move directly between client and S3-compatible storage via presigned URLs

Metadata and policy:

- live in the file manager service database

Access path:

- client accesses stable file URL
- service resolves file record
- service enforces visibility and ownership rules
- service redirects to a short-lived presigned download URL or proxies the file

## Core Components

### 1. API Service

Responsibilities:

- authenticate requests
- authorize access
- create file metadata
- issue upload part presigned URLs
- complete or abort multipart uploads
- manage folders
- manage visibility state
- return stable file URLs

### 2. PostgreSQL

Stores:

- file records
- folder hierarchy
- upload sessions
- explicit shares
- audit events
- derived metadata

### 3. Object Storage

Stores:

- actual file bytes
- multipart upload parts before completion

Rules:

- bucket private by default
- no canonical public object URL
- object keys opaque and internal

### 4. Background Workers

Responsibilities:

- cleanup stale multipart uploads
- enrich metadata
- optional virus scanning hooks
- optional thumbnail generation
- emit audit and domain events

### 5. Frontend File Manager

Responsibilities:

- folder browser
- file upload UI with multipart progress
- file move, rename, delete
- visibility controls
- organization context switching

## Trust And Auth Boundary

The service trusts the SSO as the identity provider.

Authentication flow:

1. Client sends bearer JWT
2. File manager verifies JWT signature using [`/public.pem`](/c:/Users/ThinkPad/Documents/Arnatech/file_manager/public.pem)
3. File manager validates standard claims such as `exp`, `iat`, and token type
4. File manager uses claims for authorization context

Expected JWT fields:

- `user_id`
- `org_id`
- `org_name`
- `roles`
- `permissions`
- `is_owner`

## Ownership Model

Each file has one owner scope:

- `user`
- `org`

This avoids ambiguous access semantics.

Examples:

- user avatar uploaded for personal profile: owner scope `user`
- organization document uploaded in org workspace: owner scope `org`

## Visibility Model

### V1

- `private`
- `org`
- `public`

### V2

- `shared`

The `shared` model requires explicit grants and possibly email invite resolution. It is better added after the core ownership and URL model are stable.

## File URL Model

Canonical URL:

```text
https://storage.arnatech.id/<uuid>
```

Properties:

- immutable
- independent of filename
- independent of folder
- independent of storage key
- safe to store in external services

This endpoint is backed by the application, not by directly exposing the object store key structure.

## Folder Model

Folders are metadata only.

This means:

- moving a file changes `folder_id` only
- renaming a folder does not change file URLs
- S3 key layout can be internal and stable

Folder hierarchy is represented in PostgreSQL. The S3 object key may include owner prefixes for operational clarity, but folder path must not be treated as the canonical identity.

## Storage Key Strategy

Recommended pattern:

```text
org/<org_id>/<yyyy>/<mm>/<uuid>
user/<user_id>/<yyyy>/<mm>/<uuid>
```

Optional original filename suffix:

```text
org/<org_id>/<yyyy>/<mm>/<uuid>-<sanitized-filename>
```

The key is internal only. Clients should never depend on it.

## Multipart Upload Flow

### Step 1. Initiate

Client calls `POST /files/upload`

Server:

- validates auth
- creates file record with UUID
- creates storage key
- starts S3 multipart upload
- stores upload session state
- returns file metadata and stable URL

### Step 2. Presign Parts

Client requests presigned URLs for part numbers.

Server:

- verifies upload session still valid
- issues presigned upload URLs for requested parts

### Step 3. Upload Parts

Client uploads directly to object storage.

### Step 4. Complete

Client submits completed part list with ETags.

Server:

- verifies ownership and upload status
- completes S3 multipart upload
- records final file size and metadata
- marks file active

### Step 5. Access

Consumer accesses stable file URL.

Server:

- loads file
- enforces authorization
- returns redirect to a short-lived presigned download URL or proxies response

## Suggested Django App Boundaries

### `authn`

- JWT verification
- auth context extraction

### `files`

- file metadata
- visibility rules
- rename and delete

### `folders`

- folder hierarchy
- move operations

### `uploads`

- multipart session lifecycle
- presigned URL issuance
- completion and abort

### `sharing`

- explicit grants
- future email invites

### `access`

- stable URL resolver
- download authorization

### `audit`

- event records
- audit queries

## API Style Guidance

- Prefer resource oriented REST
- Keep upload flow explicit rather than pretending multipart upload is one HTTP call
- Return stable file URL at initiation time
- Keep API errors structured and machine readable

## Security Considerations

- Bucket private by default
- Short expiry for presigned URLs
- Validate file size and MIME policy on initiation and completion
- Enforce row-level ownership checks before issuing any presigned URLs
- Do not expose raw object keys in public responses unless necessary for internal tooling
- Rate limit upload initiation and access endpoints

## Operational Concerns

- Cleanup abandoned multipart uploads on a schedule
- Store audit events for sensitive operations
- Emit structured logs with `user_id`, `org_id`, and `file_id`
- Monitor presign volume, upload completion rate, and failed completion rate

## V1 Architecture Summary

V1 should optimize for:

- correctness of auth and access control
- stable file URL contract
- reliable multipart upload
- folder based browsing
- low coupling for client services
