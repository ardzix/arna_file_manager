# SSO IAM and tenant Drive access

Human and device tokens use the same SSO permission catalogue. Request a storage
token from SSO `POST /api/v1/devices/resource-token/` with
`{"audience":"storage"}`. File Manager requires RS256, configured issuer and
audience, valid expiry and the correct principal type. Device tokens also require
matching registration/version and a live SSO introspection result. Invalid tokens
return 401, missing permissions 403, foreign/private resources 404, invalid inputs
400 and unavailable SSO inspection 503. Errors include `error`, `detail`, and
`request_id`; responses carry `X-Request-ID`.

| Operation | Permission |
| --- | --- |
| List/read/download/folder children | `storage.files.read` |
| Initiate, presign, complete or abort upload | `storage.files.create` |
| Edit metadata or move file | `storage.files.update` |
| Delete file | `storage.files.delete` |
| Publish, share or revoke share | `storage.files.share` |
| Create folder | `storage.folders.create` |

Service principals continue to use their signed storage scopes. Human/device
principals use `permissions`. Ownership never substitutes for an endpoint grant.
Public stable URLs and explicit share links retain their existing semantics.

Device uploads/folders must use `owner_scope=org`. Ownership is derived from the
verified token's organization and tenant; caller-supplied identifiers cannot
override it. `created_by_device_id` records the device actor. Authorized humans
in the same workspace can access those assets. Files cannot be moved to a folder
owned by another organization, tenant or ownership scope. Devices have no access
to personal or service-owned assets. Legacy organization assets with null tenant
stay unassigned; resolve their real tenant explicitly before migrating ownership.

## Backend configuration and release

Set `PUBLIC_KEY_PATH` to SSO's public verification key, `JWT_ISSUER`,
`JWT_AUDIENCE=storage`, `SSO_BASE_URL`, `STORAGE_PUBLIC_BASE_URL`, and dedicated
`SSO_INTROSPECTION_CLIENT_ID`/`SSO_INTROSPECTION_CLIENT_SECRET`. The active SSO
ServiceAccount must have exactly `audiences=["arna-sso-devices"]` and
`scopes=["sso.device.introspect"]`. Global accounts are for trusted platform
backends; organization/tenant constraints can narrow inspection. No service secret
belongs in device code or frontend configuration.

Every device request exchanges the inspector secret server-side and calls SSO's
`/api/v1/devices/introspect/` with the device JWT and storage audience. Results are
not cached, so revoke and storage permission changes take effect immediately.
Key-bound devices also send `Authorization: DPoP ...` and a fresh signed proof:
exact method and configured public URL, unique `jti`, timestamp and token hash
`ath`. PostgreSQL replay storage is shared across replicas.

Run committed migrations, never production `makemigrations`: `authn.0001` and
`files.0003` add replay storage, tenant ownership and device audit fields. No legacy
ownership is inferred. Deploy SSO's context/IAM/resource-token migrations first,
then File Manager with inspector credentials, then the updated frontend. Pause
affected traffic during schema/application replacement. Repository implementation
does not itself confirm a production rollout.

Jenkins currently publishes tested images with `DEPLOY=false`; pushing `main`
does not invoke its legacy rollout. `.dockerignore` excludes runtime `.env` and
private keys. Before enabling production rollout, provide runtime configuration
externally, replace the startup migration with a bounded one-off migration gate,
deploy by digest and verify the service's actual listening/proxy ports. Do not
simply flip the legacy deploy switch.

## Isolated verification

Install `requirements.txt`, then run `python scripts/test_device_access.py`.
It generates temporary RSA keys, uses an in-memory SQLite database, clears S3
credentials and mocks SSO/S3 calls. It checks migration drift and human/device
permissions, tenant isolation, upload/share workflows, token validation, revocation,
dependency failures and DPoP replay protection without production data writes.
