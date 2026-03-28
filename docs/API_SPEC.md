# API Specification

## Conventions

- All authenticated endpoints accept `Authorization: Bearer <jwt>`
- JWT is verified locally using the configured public key
- JSON is the default request and response format
- Timestamps are ISO 8601 UTC
- UUIDs are string identifiers

Base URL example:

```text
https://storage.arnatech.id/api
```

## Auth Context

Expected JWT claims include:

```json
{
  "token_type": "access",
  "user_id": "ce079f91-9d06-407a-a790-98d143956760",
  "org_id": "0fd36716-e6b8-415b-9c30-ad7127c202c3",
  "org_name": "BAF Production",
  "roles": [],
  "permissions": [],
  "is_owner": true
}
```

## Upload Workflow

### 1. Initiate Upload

`POST /files/upload`

Purpose:

- create file record
- assign canonical UUID URL
- initiate multipart upload

Request body:

```json
{
  "filename": "avatar.png",
  "size_bytes": 582314,
  "mime_type": "image/png",
  "owner_scope": "user",
  "visibility": "private",
  "folder_id": "63a4db61-c8e2-4620-8c36-e402981db4a4"
}
```

Response:

```json
{
  "file_id": "0df6d19d-4c9f-4eb1-8dca-e5fd20f3f4db",
  "url": "https://storage.arnatech.id/0df6d19d-4c9f-4eb1-8dca-e5fd20f3f4db",
  "status": "upload_pending",
  "multipart": {
    "upload_id": "s3-provider-upload-id",
    "part_size_bytes": 8388608,
    "expires_at": "2026-03-29T10:00:00Z"
  }
}
```

Notes:

- Return the stable file URL immediately
- The URL is safe for downstream services to store before upload completion

### 2. Presign Upload Parts

`POST /files/{file_id}/parts/presign`

Request body:

```json
{
  "parts": [1, 2, 3]
}
```

Response:

```json
{
  "file_id": "0df6d19d-4c9f-4eb1-8dca-e5fd20f3f4db",
  "parts": [
    {
      "part_number": 1,
      "url": "https://s3-compatible.example/upload-part-1"
    },
    {
      "part_number": 2,
      "url": "https://s3-compatible.example/upload-part-2"
    },
    {
      "part_number": 3,
      "url": "https://s3-compatible.example/upload-part-3"
    }
  ]
}
```

### 3. Complete Multipart Upload

`POST /files/{file_id}/complete`

Request body:

```json
{
  "parts": [
    {
      "part_number": 1,
      "etag": "\"etag-part-1\""
    },
    {
      "part_number": 2,
      "etag": "\"etag-part-2\""
    }
  ]
}
```

Response:

```json
{
  "file_id": "0df6d19d-4c9f-4eb1-8dca-e5fd20f3f4db",
  "url": "https://storage.arnatech.id/0df6d19d-4c9f-4eb1-8dca-e5fd20f3f4db",
  "status": "active",
  "size_bytes": 582314,
  "mime_type": "image/png"
}
```

### 4. Abort Multipart Upload

`POST /files/{file_id}/abort`

Response:

```json
{
  "file_id": "0df6d19d-4c9f-4eb1-8dca-e5fd20f3f4db",
  "status": "aborted"
}
```

## File Metadata And Management

### Get File Metadata

`GET /files/{file_id}`

Response:

```json
{
  "id": "0df6d19d-4c9f-4eb1-8dca-e5fd20f3f4db",
  "url": "https://storage.arnatech.id/0df6d19d-4c9f-4eb1-8dca-e5fd20f3f4db",
  "display_name": "avatar.png",
  "visibility": "private",
  "owner_scope": "user",
  "folder_id": "63a4db61-c8e2-4620-8c36-e402981db4a4",
  "status": "active"
}
```

### Update File Metadata

`PATCH /files/{file_id}`

Request body example:

```json
{
  "display_name": "avatar-new.png",
  "visibility": "public"
}
```

### Move File

`POST /files/{file_id}/move`

Request body:

```json
{
  "folder_id": "9c85a0ef-8e2a-4927-b77f-7c90fdb96f2b"
}
```

Response:

```json
{
  "file_id": "0df6d19d-4c9f-4eb1-8dca-e5fd20f3f4db",
  "folder_id": "9c85a0ef-8e2a-4927-b77f-7c90fdb96f2b"
}
```

### Delete File

`DELETE /files/{file_id}`

Behavior:

- soft delete file metadata
- optionally schedule storage cleanup

## Folder API

### Create Folder

`POST /folders`

Request body:

```json
{
  "name": "Profile Pictures",
  "parent_id": null,
  "owner_scope": "user"
}
```

### List Folder Children

`GET /folders/{folder_id}/children`

Response:

```json
{
  "folder": {
    "id": "63a4db61-c8e2-4620-8c36-e402981db4a4",
    "name": "Profile Pictures"
  },
  "folders": [],
  "files": [
    {
      "id": "0df6d19d-4c9f-4eb1-8dca-e5fd20f3f4db",
      "display_name": "avatar.png",
      "url": "https://storage.arnatech.id/0df6d19d-4c9f-4eb1-8dca-e5fd20f3f4db"
    }
  ]
}
```

### Update Folder

`PATCH /folders/{folder_id}`

### Delete Folder

`DELETE /folders/{folder_id}`

Behavior:

- soft delete folder
- either prevent delete if non-empty or require explicit move strategy

## Stable URL Access

### Resolve And Access File

`GET /{uuid}`

Behavior:

1. Resolve `uuid` to file record
2. Evaluate access policy
3. Return one of:
   - `302` redirect to short-lived presigned GET URL
   - proxied file stream
   - `403` if not allowed
   - `404` if not found or intentionally hidden

## Authorization Rules

### `private`

- owner only
- org admins can optionally be granted override later, but keep v1 strict unless needed

### `org`

- requester must be authenticated
- requester `org_id` must match file `owner_org_id`

### `public`

- unauthenticated access allowed if product chooses public resolver behavior
- alternatively authenticated optional but not required

### `shared`

- requester must match explicit share grant
- best deferred from v1 unless required

## Validation Rules

- reject unsupported MIME types if policy configured
- enforce max file size at initiation
- ensure completed multipart upload part list is ordered and complete
- ensure file owner scope aligns with JWT context

## Error Format

Recommended standard:

```json
{
  "error": {
    "code": "permission_denied",
    "message": "You do not have access to this file."
  }
}
```

Example error codes:

- `invalid_token`
- `permission_denied`
- `file_not_found`
- `upload_expired`
- `invalid_part_list`
- `invalid_visibility`
- `invalid_owner_scope`

## Minimal Client Flow Example

Example: SSO profile picture upload.

1. SSO frontend calls `POST /files/upload`
2. File manager returns stable URL and multipart metadata
3. Frontend uploads parts directly to S3
4. Frontend calls `POST /files/{id}/complete`
5. Frontend saves returned `url` into SSO `profile_picture`

This keeps the SSO service independent from storage implementation details.
