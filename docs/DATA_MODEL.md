# Data Model Specification

## Design Principles

- Canonical file identity is separate from physical storage
- Folder placement is mutable metadata
- Ownership is explicit and single-scoped
- Visibility is normalized and queryable
- Upload state is durable and resumable

## Core Entities

### `folders`

Represents hierarchical containers for browsing and organizing files.

Suggested fields:

- `id` UUID PK
- `parent_id` nullable FK to `folders.id`
- `owner_scope` enum: `user`, `org`
- `owner_user_id` nullable UUID
- `owner_org_id` nullable UUID
- `name` varchar
- `path_cache` text or ltree-like derived path if desired
- `created_by_user_id` UUID
- `created_at` timestamptz
- `updated_at` timestamptz
- `deleted_at` nullable timestamptz

Constraints:

- exactly one of `owner_user_id` or `owner_org_id` must be set based on `owner_scope`
- folder names may be unique per parent and owner scope

### `files`

Represents the canonical file metadata and stable identity.

Suggested fields:

- `id` UUID PK
- `folder_id` nullable FK to `folders.id`
- `owner_scope` enum: `user`, `org`
- `owner_user_id` nullable UUID
- `owner_org_id` nullable UUID
- `created_by_user_id` UUID
- `visibility` enum: `private`, `org`, `public`, `shared`
- `status` enum: `upload_pending`, `uploading`, `active`, `deleted`, `failed`, `aborted`
- `original_name` varchar
- `display_name` varchar
- `extension` varchar nullable
- `mime_type` varchar
- `size_bytes` bigint nullable until completion
- `checksum_sha256` varchar nullable
- `storage_bucket` varchar
- `storage_key` varchar unique
- `storage_version_id` varchar nullable
- `etag` varchar nullable
- `stable_url` varchar unique
- `created_at` timestamptz
- `updated_at` timestamptz
- `completed_at` nullable timestamptz
- `deleted_at` nullable timestamptz

Constraints:

- `stable_url` maps to `https://storage.arnatech.id/<id>`
- `display_name` can change without affecting `id`, `storage_key`, or `stable_url`
- exactly one owner target must be set

### `multipart_uploads`

Tracks in-progress S3 multipart upload sessions.

Suggested fields:

- `id` UUID PK
- `file_id` unique FK to `files.id`
- `provider_upload_id` varchar
- `part_size_bytes` bigint
- `parts_expected` int nullable
- `expires_at` timestamptz
- `status` enum: `initiated`, `uploading`, `completed`, `aborted`, `expired`, `failed`
- `created_at` timestamptz
- `updated_at` timestamptz

### `multipart_upload_parts`

Tracks uploaded part metadata for resumability and validation.

Suggested fields:

- `id` UUID PK
- `multipart_upload_id` FK
- `part_number` int
- `etag` varchar
- `size_bytes` bigint nullable
- `uploaded_at` timestamptz

Constraints:

- unique on `(multipart_upload_id, part_number)`

### `file_shares`

Reserved for explicit sharing support.

Suggested fields:

- `id` UUID PK
- `file_id` FK
- `subject_type` enum: `user`, `email`
- `subject_user_id` nullable UUID
- `subject_email` nullable varchar
- `permission` enum: `view`, `edit`
- `status` enum: `active`, `pending`, `revoked`
- `granted_by_user_id` UUID
- `created_at` timestamptz
- `updated_at` timestamptz

V1 note:

- this table may exist but stay unused if `shared` is deferred

### `audit_events`

Tracks security and operationally relevant actions.

Suggested fields:

- `id` UUID PK
- `actor_user_id` nullable UUID
- `actor_org_id` nullable UUID
- `event_type` varchar
- `resource_type` varchar
- `resource_id` UUID nullable
- `metadata_json` jsonb
- `created_at` timestamptz

## Recommended Enums

### `owner_scope`

- `user`
- `org`

### `visibility`

- `private`
- `org`
- `public`
- `shared`

### `file_status`

- `upload_pending`
- `uploading`
- `active`
- `failed`
- `aborted`
- `deleted`

### `multipart_status`

- `initiated`
- `uploading`
- `completed`
- `aborted`
- `expired`
- `failed`

## Ownership Rules

### User-Owned File

- `owner_scope = user`
- `owner_user_id` required
- `owner_org_id` nullable

### Org-Owned File

- `owner_scope = org`
- `owner_org_id` required
- `owner_user_id` nullable or optionally also stored as creator only

## URL Resolution Rule

The route parameter `<uuid>` must resolve to `files.id`. The `stable_url` can be derived instead of stored, but storing it makes integration responses simpler.

Recommended derivation:

```text
stable_url = https://storage.arnatech.id/<files.id>
```

## Indexing Guidance

Recommended indexes:

- `files(owner_scope, owner_user_id, status)`
- `files(owner_scope, owner_org_id, status)`
- `files(folder_id, status)`
- `files(visibility, status)`
- `files(created_by_user_id, created_at desc)`
- `multipart_uploads(file_id)`
- `multipart_uploads(status, expires_at)`
- `audit_events(resource_type, resource_id, created_at desc)`

## Soft Delete Guidance

Prefer soft delete for files and folders.

Reasons:

- avoids breaking foreign key references
- helps audit and recovery
- allows delayed storage cleanup

On delete:

- mark file deleted in DB
- asynchronously remove or archive object from storage if policy requires

## Optional Future Entities

- `file_versions`
- `access_tokens`
- `thumbnails`
- `quotas`
- `retention_policies`
- `org_permissions_overrides`

## Example `files` Record

```json
{
  "id": "0df6d19d-4c9f-4eb1-8dca-e5fd20f3f4db",
  "folder_id": "63a4db61-c8e2-4620-8c36-e402981db4a4",
  "owner_scope": "user",
  "owner_user_id": "ce079f91-9d06-407a-a790-98d143956760",
  "owner_org_id": null,
  "created_by_user_id": "ce079f91-9d06-407a-a790-98d143956760",
  "visibility": "private",
  "status": "active",
  "original_name": "avatar.png",
  "display_name": "avatar.png",
  "mime_type": "image/png",
  "size_bytes": 582314,
  "storage_bucket": "arnatech-files",
  "storage_key": "user/ce079f91-9d06-407a-a790-98d143956760/2026/03/0df6d19d-4c9f-4eb1-8dca-e5fd20f3f4db",
  "stable_url": "https://storage.arnatech.id/0df6d19d-4c9f-4eb1-8dca-e5fd20f3f4db"
}
```
