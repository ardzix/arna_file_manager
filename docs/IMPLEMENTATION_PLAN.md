# Implementation Plan

## Delivery Strategy

Build the service in vertical slices. Finish the full happy path first, then add management and hardening features.

## Phase 0: Foundation

Deliver:

- Django and DRF project skeleton
- PostgreSQL integration
- Redis and Celery setup
- S3-compatible storage configuration
- environment and settings structure
- OpenAPI generation

Acceptance:

- service boots locally
- health endpoint works
- DB migrations run
- storage client can connect

## Phase 1: Authentication Context

Deliver:

- JWT bearer auth middleware or DRF authentication class
- local signature verification using `public.pem`
- auth context extraction for `user_id`, `org_id`, and related claims

Acceptance:

- valid token authenticates
- expired or invalid token is rejected
- authenticated request exposes normalized auth context to views

## Phase 2: Files And Multipart Upload

Deliver:

- `files` table
- `multipart_uploads` table
- `multipart_upload_parts` table
- `POST /files/upload`
- `POST /files/{id}/parts/presign`
- `POST /files/{id}/complete`
- `POST /files/{id}/abort`

Acceptance:

- small and large file upload works end to end
- stable URL is returned at initiation
- completed upload becomes accessible by metadata query
- aborted upload is unusable

## Phase 3: Stable URL Resolver

Deliver:

- `GET /{uuid}` resolver
- authorization checks for `private`, `org`, and `public`
- redirect or proxy download implementation

Acceptance:

- owner can access private file
- org member can access org-visible file
- public file can be accessed per configured policy
- unauthorized access is denied

## Phase 4: Folder Management

Deliver:

- `folders` table
- create, update, delete folder endpoints
- list folder children endpoint
- move file endpoint

Acceptance:

- files can be organized by folder
- moving file does not change stable URL
- folder browsing works for personal and org scopes

## Phase 5: Metadata And Admin Operations

Deliver:

- rename file
- change visibility
- soft delete
- audit events for sensitive actions

Acceptance:

- rename does not affect access URL
- audit event written for upload, complete, move, rename, delete, visibility change

## Phase 6: Frontend File Manager

Deliver:

- authenticated file browser
- multipart upload UI with progress
- folder tree and file list
- move, rename, delete controls
- visibility management

Acceptance:

- end user can manage personal files
- end user can manage org files in current org context

## Phase 7: Hardening

Deliver:

- cleanup stale multipart sessions
- rate limiting
- file type policy
- size limits
- structured logs and metrics

Acceptance:

- stale sessions are cleaned automatically
- abuse controls are present
- operational telemetry is available

## Suggested Backend Module Order

1. settings and config
2. auth class and auth context utilities
3. file and upload models
4. upload service
5. upload endpoints
6. access resolver
7. folder models and endpoints
8. audit logging
9. UI and admin support

## Suggested Test Plan

### Unit Tests

- JWT verification
- owner scope validation
- visibility policy checks
- multipart upload state transitions

### Integration Tests

- initiate upload
- presign parts
- complete upload
- abort upload
- access stable URL
- move file without changing URL

### End-To-End Tests

- upload profile picture and save returned URL
- browse files in folder UI
- access public file
- deny access to unauthorized private file

## Risks And Mitigations

### Risk: Access Rules Become Hard To Reason About

Mitigation:

- keep ownership single-scoped
- keep authorization rules centralized
- defer `shared` until core flows are stable

### Risk: Multipart Upload Cleanup Is Neglected

Mitigation:

- add worker job and expiration timestamps from the start

### Risk: Client Services Depend On Raw Storage URLs

Mitigation:

- return only stable service URL as canonical integration contract

### Risk: Org Context Is Ambiguous

Mitigation:

- require explicit `owner_scope`
- use JWT `org_id` when scope is `org`

## Definition Of Done For V1

V1 is complete when:

- a client service can upload a file and store the returned stable URL
- users can browse and organize files in folders
- access control works for `private`, `org`, and `public`
- uploads are multipart and resumable enough for large files
- logs and audit trails exist for critical actions
