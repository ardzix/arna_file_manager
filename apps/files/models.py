import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class OwnerScope(models.TextChoices):
    USER = "user", "User"
    ORG = "org", "Organization"
    SERVICE = "service", "Service"


class Visibility(models.TextChoices):
    PRIVATE = "private", "Private"
    ORG = "org", "Organization"
    PUBLIC = "public", "Public"
    SHARED = "shared", "Shared"


class FileStatus(models.TextChoices):
    UPLOAD_PENDING = "upload_pending", "Upload Pending"
    UPLOADING = "uploading", "Uploading"
    ACTIVE = "active", "Active"
    FAILED = "failed", "Failed"
    ABORTED = "aborted", "Aborted"
    DELETED = "deleted", "Deleted"


class MultipartStatus(models.TextChoices):
    INITIATED = "initiated", "Initiated"
    UPLOADING = "uploading", "Uploading"
    COMPLETED = "completed", "Completed"
    ABORTED = "aborted", "Aborted"
    EXPIRED = "expired", "Expired"
    FAILED = "failed", "Failed"


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Folder(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children")
    owner_scope = models.CharField(max_length=10, choices=OwnerScope.choices)
    owner_user_id = models.UUIDField(null=True, blank=True)
    owner_org_id = models.UUIDField(null=True, blank=True)
    name = models.CharField(max_length=255)
    created_by_user_id = models.UUIDField()
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["owner_scope", "owner_user_id"]),
            models.Index(fields=["owner_scope", "owner_org_id"]),
            models.Index(fields=["parent"]),
        ]

    def clean(self):
        if self.owner_scope == OwnerScope.USER and not self.owner_user_id:
            raise ValidationError("owner_user_id is required for user scope.")
        if self.owner_scope == OwnerScope.ORG and not self.owner_org_id:
            raise ValidationError("owner_org_id is required for org scope.")
        if self.owner_scope == OwnerScope.USER and self.owner_org_id:
            raise ValidationError("owner_org_id must be null for user scope.")
        if self.owner_scope == OwnerScope.ORG and self.owner_user_id:
            raise ValidationError("owner_user_id must be null for org scope.")

    def __str__(self) -> str:
        return f"{self.name} ({self.owner_scope})"


class FileAsset(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    folder = models.ForeignKey(Folder, null=True, blank=True, on_delete=models.SET_NULL, related_name="files")
    owner_scope = models.CharField(max_length=10, choices=OwnerScope.choices)
    owner_user_id = models.UUIDField(null=True, blank=True)
    owner_org_id = models.UUIDField(null=True, blank=True)
    owner_service_id = models.UUIDField(null=True, blank=True)
    created_by_user_id = models.UUIDField(null=True, blank=True)
    created_by_service_id = models.UUIDField(null=True, blank=True)

    visibility = models.CharField(max_length=10, choices=Visibility.choices, default=Visibility.PRIVATE)
    status = models.CharField(max_length=20, choices=FileStatus.choices, default=FileStatus.UPLOAD_PENDING)

    original_name = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255)
    extension = models.CharField(max_length=32, blank=True, default="")
    mime_type = models.CharField(max_length=255)
    size_bytes = models.BigIntegerField(null=True, blank=True)

    storage_bucket = models.CharField(max_length=255)
    storage_key = models.CharField(max_length=1024, unique=True)
    storage_version_id = models.CharField(max_length=255, null=True, blank=True)
    etag = models.CharField(max_length=255, null=True, blank=True)
    stable_url = models.URLField(max_length=512, unique=True)

    completed_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["owner_scope", "owner_user_id", "status"]),
            models.Index(fields=["owner_scope", "owner_org_id", "status"]),
            models.Index(fields=["owner_scope", "owner_service_id", "status"]),
            models.Index(fields=["folder", "status"]),
            models.Index(fields=["visibility", "status"]),
        ]

    def _build_stable_url(self) -> str:
        return f"{settings.STORAGE_PUBLIC_BASE_URL.rstrip('/')}/{self.id}"

    def full_clean(self, exclude=None, validate_unique=True, validate_constraints=True):
        if not self.stable_url and self.id:
            self.stable_url = self._build_stable_url()
        super().full_clean(
            exclude=exclude,
            validate_unique=validate_unique,
            validate_constraints=validate_constraints,
        )

    def clean(self):
        if not self.stable_url and self.id:
            self.stable_url = self._build_stable_url()

        if self.owner_scope == OwnerScope.USER and not self.owner_user_id:
            raise ValidationError("owner_user_id is required for user scope.")
        if self.owner_scope == OwnerScope.ORG and not self.owner_org_id:
            raise ValidationError("owner_org_id is required for org scope.")
        if self.owner_scope == OwnerScope.SERVICE and not self.owner_service_id:
            raise ValidationError("owner_service_id is required for service scope.")
        if self.owner_scope == OwnerScope.USER and self.owner_org_id:
            raise ValidationError("owner_org_id must be null for user scope.")
        if self.owner_scope == OwnerScope.ORG and self.owner_user_id:
            raise ValidationError("owner_user_id must be null for org scope.")
        if self.owner_scope != OwnerScope.SERVICE and self.owner_service_id:
            raise ValidationError("owner_service_id is only valid for service scope.")
        if self.visibility == Visibility.ORG and self.owner_scope != OwnerScope.ORG:
            raise ValidationError("org visibility is only valid for org-owned files.")

    def save(self, *args, **kwargs):
        if not self.stable_url:
            self.stable_url = self._build_stable_url()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.display_name} ({self.id})"


class MultipartUpload(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.OneToOneField(FileAsset, on_delete=models.CASCADE, related_name="multipart_upload")
    provider_upload_id = models.CharField(max_length=255)
    part_size_bytes = models.BigIntegerField()
    parts_expected = models.IntegerField(null=True, blank=True)
    expires_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=MultipartStatus.choices, default=MultipartStatus.INITIATED)

    class Meta:
        indexes = [models.Index(fields=["status", "expires_at"])]

    def __str__(self) -> str:
        return f"{self.file_id} / {self.provider_upload_id}"


class MultipartUploadPart(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    multipart_upload = models.ForeignKey(MultipartUpload, on_delete=models.CASCADE, related_name="parts")
    part_number = models.IntegerField()
    etag = models.CharField(max_length=255)
    size_bytes = models.BigIntegerField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("multipart_upload", "part_number")

    def __str__(self) -> str:
        return f"{self.multipart_upload_id}:{self.part_number}"


class FileShare(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.ForeignKey(FileAsset, on_delete=models.CASCADE, related_name="shares")
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_by_user_id = models.UUIDField(null=True, blank=True)
    created_by_service_id = models.UUIDField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["token_hash", "expires_at", "revoked_at"])]
