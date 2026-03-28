from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import FileAsset, FileStatus, Folder, MultipartStatus, MultipartUpload, MultipartUploadPart, OwnerScope, Visibility
from .serializers import (
    CompleteUploadSerializer,
    FileMoveSerializer,
    FileSerializer,
    FileUpdateSerializer,
    FolderCreateSerializer,
    PresignPartsSerializer,
    UploadInitiateSerializer,
)
from .services import S3MultipartService


def _is_owner(principal, file_obj: FileAsset) -> bool:
    if file_obj.owner_scope == OwnerScope.USER:
        return str(file_obj.owner_user_id) == str(principal.user_id)
    return str(file_obj.owner_org_id) == str(principal.org_id)


def _can_read(principal, file_obj: FileAsset) -> bool:
    if file_obj.visibility == Visibility.PUBLIC:
        return True
    if principal is None or not getattr(principal, "is_authenticated", False):
        return False
    if _is_owner(principal, file_obj):
        return True
    if file_obj.visibility == Visibility.ORG and str(file_obj.owner_org_id) == str(principal.org_id):
        return True
    return False


def _check_file_write_access(principal, file_obj: FileAsset):
    if not _is_owner(principal, file_obj):
        return Response({"error": {"code": "permission_denied", "message": "Not allowed for this file."}}, status=403)
    return None


def _check_folder_access(principal, folder: Folder) -> bool:
    if folder.owner_scope == OwnerScope.USER:
        return str(folder.owner_user_id) == str(principal.user_id)
    return str(folder.owner_org_id) == str(principal.org_id)


class UploadInitiateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = UploadInitiateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        principal = request.user
        file_id = FileAsset._meta.get_field("id").default()
        owner_scope = data["owner_scope"]
        owner_id = principal.user_id if owner_scope == OwnerScope.USER else principal.org_id

        s3 = S3MultipartService()
        storage_key = s3.create_storage_key(owner_scope=owner_scope, owner_id=str(owner_id), file_id=file_id)
        upload_id = s3.initiate_multipart_upload(storage_key=storage_key, mime_type=data["mime_type"])

        folder = None
        folder_id = data.get("folder_id")
        if folder_id:
            folder = get_object_or_404(Folder, id=folder_id, deleted_at__isnull=True)
            if not _check_folder_access(principal, folder):
                return Response({"error": {"code": "permission_denied", "message": "Folder access denied."}}, status=403)

        file_obj = FileAsset(
            id=file_id,
            folder=folder,
            owner_scope=owner_scope,
            owner_user_id=principal.user_id if owner_scope == OwnerScope.USER else None,
            owner_org_id=principal.org_id if owner_scope == OwnerScope.ORG else None,
            created_by_user_id=principal.user_id,
            visibility=data["visibility"],
            status=FileStatus.UPLOAD_PENDING,
            original_name=data["filename"],
            display_name=data["filename"],
            mime_type=data["mime_type"],
            size_bytes=data["size_bytes"],
            storage_bucket=s3.bucket,
            storage_key=storage_key,
            stable_url="",
        )
        file_obj.full_clean()
        file_obj.save()

        multipart = MultipartUpload.objects.create(
            file=file_obj,
            provider_upload_id=upload_id,
            part_size_bytes=settings.S3_DEFAULT_PART_SIZE_BYTES,
            expires_at=s3.upload_expires_at(),
            status=MultipartStatus.INITIATED,
        )

        return Response(
            {
                "file_id": str(file_obj.id),
                "url": file_obj.stable_url,
                "status": file_obj.status,
                "multipart": {
                    "upload_id": multipart.provider_upload_id,
                    "part_size_bytes": multipart.part_size_bytes,
                    "expires_at": multipart.expires_at,
                },
            },
            status=status.HTTP_201_CREATED,
        )


class PresignPartsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, file_id):
        file_obj = get_object_or_404(FileAsset, id=file_id, deleted_at__isnull=True)
        denied = _check_file_write_access(request.user, file_obj)
        if denied:
            return denied

        multipart = get_object_or_404(MultipartUpload, file=file_obj)
        if multipart.status in {MultipartStatus.COMPLETED, MultipartStatus.ABORTED, MultipartStatus.EXPIRED}:
            return Response({"error": {"code": "upload_expired", "message": "Upload session is not active."}}, status=400)
        if multipart.expires_at <= timezone.now():
            multipart.status = MultipartStatus.EXPIRED
            multipart.save(update_fields=["status", "updated_at"])
            return Response({"error": {"code": "upload_expired", "message": "Upload session expired."}}, status=400)

        serializer = PresignPartsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        s3 = S3MultipartService()
        parts = []
        for part_number in serializer.validated_data["parts"]:
            parts.append(
                {
                    "part_number": part_number,
                    "url": s3.presign_upload_part(
                        storage_key=file_obj.storage_key,
                        upload_id=multipart.provider_upload_id,
                        part_number=part_number,
                    ),
                }
            )

        multipart.status = MultipartStatus.UPLOADING
        multipart.save(update_fields=["status", "updated_at"])
        file_obj.status = FileStatus.UPLOADING
        file_obj.save(update_fields=["status", "updated_at"])

        return Response({"file_id": str(file_obj.id), "parts": parts})


class UploadCompleteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, file_id):
        file_obj = get_object_or_404(FileAsset, id=file_id, deleted_at__isnull=True)
        denied = _check_file_write_access(request.user, file_obj)
        if denied:
            return denied

        multipart = get_object_or_404(MultipartUpload, file=file_obj)
        if multipart.status in {MultipartStatus.COMPLETED, MultipartStatus.ABORTED}:
            return Response({"error": {"code": "invalid_state", "message": "Upload cannot be completed."}}, status=400)

        serializer = CompleteUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        parts = serializer.validated_data["parts"]

        for part in parts:
            MultipartUploadPart.objects.update_or_create(
                multipart_upload=multipart,
                part_number=part["part_number"],
                defaults={"etag": part["etag"]},
            )

        s3 = S3MultipartService()
        completion_parts = [{"PartNumber": p["part_number"], "ETag": p["etag"]} for p in parts]
        completion = s3.complete_multipart_upload(
            storage_key=file_obj.storage_key,
            upload_id=multipart.provider_upload_id,
            parts=completion_parts,
        )

        file_obj.status = FileStatus.ACTIVE
        file_obj.etag = completion.get("ETag")
        file_obj.storage_version_id = completion.get("VersionId")
        file_obj.completed_at = timezone.now()
        file_obj.save(update_fields=["status", "etag", "storage_version_id", "completed_at", "updated_at"])

        multipart.status = MultipartStatus.COMPLETED
        multipart.save(update_fields=["status", "updated_at"])

        return Response(
            {
                "file_id": str(file_obj.id),
                "url": file_obj.stable_url,
                "status": file_obj.status,
                "size_bytes": file_obj.size_bytes,
                "mime_type": file_obj.mime_type,
            }
        )


class UploadAbortView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, file_id):
        file_obj = get_object_or_404(FileAsset, id=file_id, deleted_at__isnull=True)
        denied = _check_file_write_access(request.user, file_obj)
        if denied:
            return denied

        multipart = get_object_or_404(MultipartUpload, file=file_obj)
        if multipart.status == MultipartStatus.ABORTED:
            return Response({"file_id": str(file_obj.id), "status": FileStatus.ABORTED})

        s3 = S3MultipartService()
        s3.abort_multipart_upload(storage_key=file_obj.storage_key, upload_id=multipart.provider_upload_id)

        multipart.status = MultipartStatus.ABORTED
        multipart.save(update_fields=["status", "updated_at"])
        file_obj.status = FileStatus.ABORTED
        file_obj.save(update_fields=["status", "updated_at"])

        return Response({"file_id": str(file_obj.id), "status": file_obj.status})


class FileDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, file_id):
        file_obj = get_object_or_404(FileAsset, id=file_id, deleted_at__isnull=True)
        if not _can_read(request.user, file_obj):
            return Response({"error": {"code": "permission_denied", "message": "Access denied."}}, status=403)
        return Response(FileSerializer(file_obj).data)

    def patch(self, request, file_id):
        file_obj = get_object_or_404(FileAsset, id=file_id, deleted_at__isnull=True)
        denied = _check_file_write_access(request.user, file_obj)
        if denied:
            return denied

        serializer = FileUpdateSerializer(instance=file_obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(FileSerializer(file_obj).data)

    def delete(self, request, file_id):
        file_obj = get_object_or_404(FileAsset, id=file_id, deleted_at__isnull=True)
        denied = _check_file_write_access(request.user, file_obj)
        if denied:
            return denied
        file_obj.status = FileStatus.DELETED
        file_obj.deleted_at = timezone.now()
        file_obj.save(update_fields=["status", "deleted_at", "updated_at"])
        return Response(status=204)


class FileMoveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, file_id):
        file_obj = get_object_or_404(FileAsset, id=file_id, deleted_at__isnull=True)
        denied = _check_file_write_access(request.user, file_obj)
        if denied:
            return denied

        serializer = FileMoveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        folder = get_object_or_404(Folder, id=serializer.validated_data["folder_id"], deleted_at__isnull=True)

        if not _check_folder_access(request.user, folder):
            return Response({"error": {"code": "permission_denied", "message": "Folder access denied."}}, status=403)

        file_obj.folder = folder
        file_obj.save(update_fields=["folder", "updated_at"])
        return Response({"file_id": str(file_obj.id), "folder_id": str(folder.id)})


class FolderCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = FolderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        owner_scope = serializer.validated_data["owner_scope"]
        principal = request.user
        owner_user_id = principal.user_id if owner_scope == OwnerScope.USER else None
        owner_org_id = principal.org_id if owner_scope == OwnerScope.ORG else None
        if owner_scope == OwnerScope.ORG and not owner_org_id:
            return Response({"error": {"code": "invalid_owner_scope", "message": "org_id is required for org scope."}}, status=400)

        folder = serializer.save(
            owner_user_id=owner_user_id,
            owner_org_id=owner_org_id,
            created_by_user_id=principal.user_id,
        )
        return Response(FolderCreateSerializer(folder).data, status=201)


class FolderChildrenView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, folder_id):
        folder = get_object_or_404(Folder, id=folder_id, deleted_at__isnull=True)
        if not _check_folder_access(request.user, folder):
            return Response({"error": {"code": "permission_denied", "message": "Folder access denied."}}, status=403)

        child_folders = folder.children.filter(deleted_at__isnull=True).order_by("name")
        files = folder.files.filter(deleted_at__isnull=True).exclude(status=FileStatus.DELETED).order_by("display_name")
        return Response(
            {
                "folder": {"id": str(folder.id), "name": folder.name},
                "folders": [{"id": str(item.id), "name": item.name} for item in child_folders],
                "files": [{"id": str(item.id), "display_name": item.display_name, "url": item.stable_url} for item in files],
            }
        )


@api_view(["GET"])
@permission_classes([AllowAny])
def file_resolve_view(request, file_id):
    file_obj = get_object_or_404(FileAsset, id=file_id, deleted_at__isnull=True)
    principal = getattr(request, "user", None)
    if not _can_read(principal, file_obj):
        return Response({"error": {"code": "permission_denied", "message": "Access denied."}}, status=403)

    s3 = S3MultipartService()
    return HttpResponseRedirect(redirect_to=s3.presign_download_url(file_obj.storage_key))
