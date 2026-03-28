# Product Requirements Document

## Product Name

ArnaTech File Manager Service

## Summary

Build a centralized file service that can be used by multiple internal products. The service must let client applications upload files and receive a stable URL string that can later be stored in their own models. The same files must also be manageable through a file manager interface with folders, ownership, and visibility controls.

Example:

- The SSO service stores `profile_picture` as a URL field
- A user uploads a profile image through the file manager flow
- The file manager returns a canonical URL such as `https://storage.arnatech.id/<uuid>`
- The SSO service stores that URL string without needing to manage storage itself

## Problem Statement

Multiple services need a standard way to store and reference files. Today, each service would otherwise need to solve:

- object storage integration
- upload performance
- access control
- folder organization
- public and private access
- sharing to people or teams
- URL stability over time

This creates duplicated logic and inconsistent behavior.

## Goals

- Provide one upload system for all internal services
- Return a stable immutable file URL immediately after upload initiation
- Support large files through chunked multipart uploads
- Support direct browser or client to S3-compatible storage upload using presigned URLs
- Support file browsing and management by folder
- Support personal ownership and organization ownership
- Support `private`, `org`, `public`, and later `shared` visibility models
- Reuse the existing SSO JWT for identity and organization context

## Non-Goals For V1

- Real-time collaborative editing
- Document editing inside the browser
- Full-text indexing of document content
- Public anonymous upload links
- Cross-tenant external collaboration as the primary workflow
- Hard multi-region storage replication

## Primary Users

- End users uploading and managing their files
- Internal applications that need a file URL after upload
- Organization owners and admins managing organization-visible files
- Future support and ops teams investigating file access and audit records

## Core Use Cases

### 1. App Upload And Save URL

An internal service needs a file URL to store in its own record.

Example:

- user opens SSO profile form
- user uploads an avatar
- file manager returns `https://storage.arnatech.id/<uuid>`
- SSO saves that URL in `profile_picture`

### 2. Personal File Management

A user uploads files into personal folders and can:

- browse folders
- rename files
- move files
- delete files
- make files public or private

### 3. Organization File Management

A user uploads or manages files owned by an organization and can:

- browse organization folders
- restrict files to the active organization
- expose files to the whole org
- later share to selected people

### 4. Large File Upload

A user uploads large files reliably using chunked multipart upload with retry and resume support.

## Functional Requirements

### Authentication And Identity

- Every authenticated request uses bearer JWT from the existing SSO
- The service verifies JWT signature using the local public key
- The service uses JWT claims such as `user_id`, `org_id`, `org_name`, `roles`, `permissions`, and `is_owner`
- The service does not manage passwords or sessions itself

### File Identity

- Each file gets a UUID at creation time
- Canonical file URL is `https://storage.arnatech.id/<uuid>`
- Canonical URL does not change when a file is renamed or moved

### Upload

- Uploads must support multipart chunked transfer
- Clients upload directly to S3-compatible storage using presigned URLs
- The service tracks upload state from initiation through completion or abort
- Uploads should support parallel part upload

### File Management

- Files can belong to a user or an organization
- Files can be assigned to folders
- Folders are metadata only and do not control the canonical URL
- Users can rename and move files without changing the stable URL

### Visibility And Access

V1 visibility:

- `private`
- `org`
- `public`

Planned next visibility:

- `shared`

V1 behavior:

- `private`: owner only
- `org`: any authenticated member in the owner org context
- `public`: accessible by public URL or via a public redirect endpoint

### Download

- Access to a file should resolve through the file manager service
- Raw S3 object URLs must not be used as permanent URLs
- Service may redirect to short-lived presigned GET URLs

### Auditability

- Log file creation, completion, rename, move, delete, visibility change, and download access
- Keep enough metadata to investigate who accessed what and when

## Non-Functional Requirements

- Support large files efficiently
- Avoid routing file bytes through the application server where possible
- Keep bucket private by default
- Preserve URL stability
- Enforce authorization deterministically
- Provide clear API contracts for internal service integration
- Be easy for humans and AI agents to maintain

## Success Metrics

- Internal service can upload and persist returned URL with minimal custom code
- Upload success rate for large files is high
- Moving or renaming files does not break stored links
- Authorization behavior is consistent across personal and org contexts
- Time to integrate a new client service is low

## Open Questions

- Should v1 support sharing to emails outside the current organization?
- Should organization admins have elevated visibility over all org files?
- Should public access be direct or always mediated through the service?
- Should file versioning be introduced in v1 or postponed?

## Recommended V1 Scope

- JWT auth with local signature verification
- Multipart upload with presigned part URLs
- Stable UUID file URLs
- Personal and org ownership
- Folder browsing and file move or rename
- Visibility modes: `private`, `org`, `public`
- Basic audit log
- Admin and ops visibility through database and logs

## Deferred Scope

- Email invite based sharing
- External users outside org
- Version history
- Recycle bin
- Search indexing
- Preview and thumbnail pipelines
