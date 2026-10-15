# File Manager production release

Jenkins `production/arna-file-manager` checks out the configured `main` SCM with
the job's existing Git credentials. It tests the exact image before publishing,
then validates configuration, migrates once and rolls the existing `file_manager`
service by immutable digest. The production release job defaults `DEPLOY=true`;
disable it for a build-only run. Job concurrency and a manager lock serialize
releases. The approved manager is `arnatech.id` and image platform Linux/amd64.

Existing credential IDs stay unchanged: `file-manager-env`, `sso_public_pem`,
`stag-arnatech-sa-01`, `ard-dockerhub`. Add the backend-only
`SSO_INTROSPECTION_CLIENT_ID` and `SSO_INTROSPECTION_CLIENT_SECRET` to the complete
runtime env file. Configure `JWT_AUDIENCE=storage`,
`JWT_ISSUER=https://sso.arnatech.id`, `SSO_BASE_URL=https://sso.arnatech.id`.
The inspector account must have exactly audience `arna-sso-devices` and scope
`sso.device.introspect`. Do not give that secret to a device or frontend.

Keep every existing DB/object-store setting. Validation refuses missing settings,
changed DB binding, changed S3 endpoint/bucket/credentials, debug or demo seeding.
The SSO public key is checked against the existing runtime and is not rotated.
SSO inspector authentication and a negative device introspection must succeed
before any migration. No tenant role, grant, ownership inference or DB privilege
repair is performed by this pipeline.

Apply committed schema migrations, including `authn.0001_initial` and
`files.0003_fileasset_created_by_device_id_and_more`, as a bounded one-off Swarm
task with the same image digest, full runtime secret and existing overlay as
the release. Failure blocks rollout. API startup does not migrate or seed data.
Legacy files/folders whose tenant is null remain unassigned; deployment does not
make them belong to a guessed tenant or copy them into a device's workspace.

Runtime configuration and public key use immutable Swarm secrets. Image build
context contains neither uploaded credentials nor PEMs. Existing service/network
and ports are preserved, including gunicorn's internal listening port 8001;
the public HTTPS proxy uses the existing upstream. No service deletion/recreation,
Swarm initialization, database role changes or object-store writes are needed.

The release verifies live digest, running singleton API with readiness, committed
migrations, SSO inspector auth, public health and anonymous private-list rejection.
Rollout failures trigger/observe recovery toward the previous image/configuration.
Previous specs are retained privately in the manager release folder under
`/root/arnatech-releases/storage-<release-id>/`. Image rollback does not undo
additive migrations. Existing old inline env values are removed from the new
service spec and remain only in protected recovery evidence/previous spec.

Synthetic tests use temporary keys and mocked SSO/S3; no production file is
created, uploaded, shared, moved or deleted. Tests run on SQLite and isolated
PostgreSQL, including exact IAM grants and org/tenant isolation. Uploaded runtime
env/public-key/registry files are removed after the job; immutable runtime secrets
and recovery evidence remain available.

For device root listing, use:

```http
GET https://storage.arnatech.id/api/v1/folders/root/children?owner_scope=org
Authorization: Bearer <storage resource token>
```

The legacy `/api/` alias remains available. A device request with
`owner_scope=user` receives a clear 400; personal ownership is not assigned to
devices. The token comes from SSO `devices/resource-token/` with audience storage,
not directly from device pairing or from the Commerce exchange.
