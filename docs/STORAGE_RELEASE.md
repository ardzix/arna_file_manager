# File Manager production release

Jenkins `production/arna-file-manager` checks out the configured `main` SCM with
the job's existing Git credentials. It tests the exact image before publishing,
then validates configuration, migrates once and rolls the existing `file_manager`
service by immutable digest. The release job defaults `DEPLOY=false`;
enable it only for an intended rollout. Job concurrency and a manager lock serialize
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

## Cloud build and Portainer visibility

`USE_DOCKER_CLOUD=true` selects the existing `arnatechid/default` Docker Build
Cloud endpoint on the Jenkins agent. The agent needs a cloud-capable Buildx
plugin; the manager does not need Buildx. The pipeline registers the endpoint in
a private per-build Docker/Buildx configuration, exports a Linux/amd64 image
archive, and transfers it to the manager using pinned SSH. It never sends the
runtime env or SSO key to Build Cloud. Cloud failure stops the job. An operator
can explicitly select `USE_DOCKER_CLOUD=false` for a recorded manager-local build;
there is no automatic fallback. This release intentionally targets the existing
amd64 production node and does not claim an untested arm64 artifact.

Before any registry publication, the manager checks archive SHA-256, image
revision/architecture, absence of embedded configuration, isolated PostgreSQL
application tests and release guards. The pushed/pulled image ID must equal the
tested image ID. Release evidence includes `build_backend` and immutable digest.
See [Docker's image export contract](https://docs.docker.com/reference/cli/docker/buildx/build/)
and [Build Cloud setup](https://docs.docker.com/build-cloud/setup/).

The full runtime env credential is bound only in the configuration/migration
stage. It is parsed privately and mounted as release-specific Swarm secret
`/run/secrets/storage_runtime` (mode 0400). The new service spec contains only
`STORAGE_RUNTIME_SECRET_PATH=/run/secrets/storage_runtime`; every old inline env
is explicitly removed. Post-roll verification rejects leaked config keys in
either the Swarm spec or container inspect environment and rejects incorrect
secret mounts. Subsequent releases read the old private secret for DB/S3
comparison, so moving away from inline env does not break preservation checks.

Portainer will show the secret names and harmless path pointer, not the DB/S3/SSO
values in the container environment panel. Docker/host administrators can still
read mounted secrets through container access; this is not a boundary against
host administrators. The previous working spec/config is retained privately for
rollback, so historical inline values in Swarm's previous spec may remain visible
to administrators until recovery retention is deliberately retired. Deployment
does not erase old Portainer history or rotate credentials.

For device root listing, use:

```http
GET https://storage.arnatech.id/api/v1/folders/root/children?owner_scope=org
Authorization: Bearer <storage resource token>
```

The legacy `/api/` alias remains available. A device request with
`owner_scope=user` receives a clear 400; personal ownership is not assigned to
devices. The token comes from SSO `devices/resource-token/` with audience storage,
not directly from device pairing or from the Commerce exchange.
