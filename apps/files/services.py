import uuid
from datetime import timedelta

import boto3
from botocore.client import BaseClient
from django.conf import settings
from django.utils import timezone


class S3MultipartService:
    def __init__(self) -> None:
        self.bucket = settings.S3_BUCKET_NAME
        self.expires_seconds = settings.S3_PRESIGN_EXPIRES_SECONDS

    def _enabled(self) -> bool:
        return bool(settings.S3_ACCESS_KEY_ID and settings.S3_SECRET_ACCESS_KEY)

    def _client(self) -> BaseClient:
        return boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            region_name=settings.S3_REGION_NAME,
            aws_access_key_id=settings.S3_ACCESS_KEY_ID,
            aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
        )

    def create_storage_key(self, owner_scope: str, owner_id: str, file_id: uuid.UUID) -> str:
        now = timezone.now()
        return f"{owner_scope}/{owner_id}/{now.year:04d}/{now.month:02d}/{file_id}"

    def initiate_multipart_upload(self, storage_key: str, mime_type: str) -> str:
        if not self._enabled():
            return f"dev-upload-{uuid.uuid4()}"
        response = self._client().create_multipart_upload(
            Bucket=self.bucket,
            Key=storage_key,
            ContentType=mime_type,
        )
        return response["UploadId"]

    def presign_upload_part(self, storage_key: str, upload_id: str, part_number: int) -> str:
        if not self._enabled():
            return f"https://example.local/upload/{upload_id}/{part_number}"
        return self._client().generate_presigned_url(
            ClientMethod="upload_part",
            Params={
                "Bucket": self.bucket,
                "Key": storage_key,
                "UploadId": upload_id,
                "PartNumber": part_number,
            },
            ExpiresIn=self.expires_seconds,
        )

    def complete_multipart_upload(self, storage_key: str, upload_id: str, parts: list[dict]) -> dict:
        if not self._enabled():
            return {"ETag": f"dev-etag-{uuid.uuid4()}", "VersionId": None}
        response = self._client().complete_multipart_upload(
            Bucket=self.bucket,
            Key=storage_key,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )
        return {"ETag": response.get("ETag"), "VersionId": response.get("VersionId")}

    def abort_multipart_upload(self, storage_key: str, upload_id: str) -> None:
        if not self._enabled():
            return
        self._client().abort_multipart_upload(Bucket=self.bucket, Key=storage_key, UploadId=upload_id)

    def presign_download_url(self, storage_key: str) -> str:
        if not self._enabled():
            return f"https://example.local/download/{storage_key}"
        return self._client().generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": self.bucket, "Key": storage_key},
            ExpiresIn=self.expires_seconds,
        )

    def upload_expires_at(self):
        return timezone.now() + timedelta(seconds=self.expires_seconds)
