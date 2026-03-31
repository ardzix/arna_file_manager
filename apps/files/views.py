from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.conf import settings
from botocore.exceptions import ClientError
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
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


OWNER_SCOPE_QUERY_PARAM = openapi.Parameter(
    "owner_scope",
    openapi.IN_QUERY,
    description="Owner scope filter. Defaults to user.",
    type=openapi.TYPE_STRING,
    enum=[OwnerScope.USER, OwnerScope.ORG],
)

FOLDER_ID_QUERY_PARAM = openapi.Parameter(
    "folder_id",
    openapi.IN_QUERY,
    description="Optional folder ID. If omitted, returns files in root.",
    type=openapi.TYPE_STRING,
    format=openapi.FORMAT_UUID,
)


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

    @swagger_auto_schema(
        operation_summary="Initiate multipart upload",
        operation_description=(
            "Create file metadata and initialize multipart upload session. "
            "Returns immutable file URL, upload_id, and default part_size_bytes."
        ),
        request_body=UploadInitiateSerializer,
        responses={201: openapi.Response("Upload initiated")},
    )
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

    @swagger_auto_schema(
        operation_summary="Get presigned part URLs",
        operation_description=(
            "Request presigned URLs for one or more part numbers. "
            "Client uploads each part directly to object storage via HTTP PUT."
        ),
        request_body=PresignPartsSerializer,
        responses={200: openapi.Response("Presigned URLs returned")},
    )
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

    @swagger_auto_schema(
        operation_summary="Complete multipart upload",
        operation_description=(
            "Finalize multipart upload after all parts are uploaded. "
            "Payload must include every uploaded part_number with its ETag."
        ),
        request_body=CompleteUploadSerializer,
        responses={200: openapi.Response("Upload completed")},
    )
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

    @swagger_auto_schema(
        operation_summary="Abort multipart upload",
        operation_description=(
            "Abort an in-progress multipart upload and mark file status as aborted."
        ),
        responses={200: openapi.Response("Upload aborted")},
    )
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

    @swagger_auto_schema(
        operation_summary="Get file metadata",
        operation_description=(
            "Read metadata for a single file by file_id. "
            "Access is checked against owner and visibility policy."
        ),
        responses={200: FileSerializer},
    )
    def get(self, request, file_id):
        file_obj = get_object_or_404(FileAsset, id=file_id, deleted_at__isnull=True)
        if not _can_read(request.user, file_obj):
            return Response({"error": {"code": "permission_denied", "message": "Access denied."}}, status=403)
        return Response(FileSerializer(file_obj).data)

    @swagger_auto_schema(
        operation_summary="Update file metadata",
        operation_description=(
            "Update editable metadata fields (currently display_name and visibility)."
        ),
        request_body=FileUpdateSerializer,
        responses={200: FileSerializer},
    )
    def patch(self, request, file_id):
        file_obj = get_object_or_404(FileAsset, id=file_id, deleted_at__isnull=True)
        denied = _check_file_write_access(request.user, file_obj)
        if denied:
            return denied

        serializer = FileUpdateSerializer(instance=file_obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(FileSerializer(file_obj).data)

    @swagger_auto_schema(
        operation_summary="Delete file",
        operation_description=(
            "Delete file metadata and hard-delete object from S3-compatible storage by default."
        ),
        responses={204: "Deleted"},
    )
    def delete(self, request, file_id):
        file_obj = get_object_or_404(FileAsset, id=file_id, deleted_at__isnull=True)
        denied = _check_file_write_access(request.user, file_obj)
        if denied:
            return denied

        if settings.S3_HARD_DELETE_ON_FILE_DELETE:
            s3 = S3MultipartService()
            try:
                s3.delete_object(storage_key=file_obj.storage_key, version_id=file_obj.storage_version_id)
            except ClientError:
                return Response(
                    {
                        "error": {
                            "code": "storage_delete_failed",
                            "message": "Failed to delete file object from storage.",
                        }
                    },
                    status=503,
                )

        file_obj.status = FileStatus.DELETED
        file_obj.deleted_at = timezone.now()
        file_obj.save(update_fields=["status", "deleted_at", "updated_at"])
        return Response(status=204)


class FileMoveView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Move file to folder",
        operation_description=(
            "Move a file into another folder by folder_id. "
            "This updates metadata only and does not change immutable file URL."
        ),
        request_body=FileMoveSerializer,
        responses={200: openapi.Response("File moved")},
    )
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


class FileListView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="List files from root or folder",
        operation_description=(
            "List files filtered by owner_scope and optional folder_id. "
            "If folder_id is omitted, returns files in root (folder is null)."
        ),
        manual_parameters=[OWNER_SCOPE_QUERY_PARAM, FOLDER_ID_QUERY_PARAM],
        responses={200: FileSerializer(many=True)},
    )
    def get(self, request):
        principal = request.user
        owner_scope = request.query_params.get("owner_scope", OwnerScope.USER)
        folder_id = request.query_params.get("folder_id")

        if owner_scope not in {OwnerScope.USER, OwnerScope.ORG}:
            return Response({"error": {"code": "invalid_owner_scope", "message": "owner_scope must be user or org."}}, status=400)
        if owner_scope == OwnerScope.ORG and not principal.org_id:
            return Response({"error": {"code": "invalid_owner_scope", "message": "org_id is required for org scope."}}, status=400)

        files = FileAsset.objects.filter(deleted_at__isnull=True).exclude(status=FileStatus.DELETED)
        if owner_scope == OwnerScope.USER:
            files = files.filter(owner_scope=OwnerScope.USER, owner_user_id=principal.user_id)
        else:
            files = files.filter(owner_scope=OwnerScope.ORG, owner_org_id=principal.org_id)

        if folder_id:
            files = files.filter(folder_id=folder_id)
        else:
            files = files.filter(folder__isnull=True)

        files = files.order_by("display_name")
        return Response(FileSerializer(files, many=True).data)


class FolderCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Create folder",
        operation_description=(
            "Create a folder in current owner scope. "
            "Use parent field for nested folder; null means create in root."
        ),
        request_body=FolderCreateSerializer,
        responses={201: FolderCreateSerializer},
    )
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

    @swagger_auto_schema(
        operation_summary="List folders and files inside folder",
        operation_description=(
            "List direct children (folders and files) inside a specific folder."
        ),
        responses={200: openapi.Response("Folder children returned")},
    )
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


class RootChildrenView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="List root folders and files",
        operation_description=(
            "List top-level folders and files for selected owner_scope."
        ),
        manual_parameters=[OWNER_SCOPE_QUERY_PARAM],
        responses={200: openapi.Response("Root children returned")},
    )
    def get(self, request):
        principal = request.user
        owner_scope = request.query_params.get("owner_scope", OwnerScope.USER)

        if owner_scope not in {OwnerScope.USER, OwnerScope.ORG}:
            return Response({"error": {"code": "invalid_owner_scope", "message": "owner_scope must be user or org."}}, status=400)
        if owner_scope == OwnerScope.ORG and not principal.org_id:
            return Response({"error": {"code": "invalid_owner_scope", "message": "org_id is required for org scope."}}, status=400)

        folders = Folder.objects.filter(parent__isnull=True, deleted_at__isnull=True)
        files = FileAsset.objects.filter(folder__isnull=True, deleted_at__isnull=True).exclude(status=FileStatus.DELETED)
        if owner_scope == OwnerScope.USER:
            folders = folders.filter(owner_scope=OwnerScope.USER, owner_user_id=principal.user_id)
            files = files.filter(owner_scope=OwnerScope.USER, owner_user_id=principal.user_id)
        else:
            folders = folders.filter(owner_scope=OwnerScope.ORG, owner_org_id=principal.org_id)
            files = files.filter(owner_scope=OwnerScope.ORG, owner_org_id=principal.org_id)

        folders = folders.order_by("name")
        files = files.order_by("display_name")
        return Response(
            {
                "folder": None,
                "folders": [{"id": str(item.id), "name": item.name} for item in folders],
                "files": [{"id": str(item.id), "display_name": item.display_name, "url": item.stable_url} for item in files],
            }
        )


class FileResolveView(APIView):
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_summary="Resolve stable file URL",
        operation_description=(
            "Default behavior is HTTP 302 redirect to a short-lived presigned download URL. "
            "If request Accept header contains application/json (for example from Swagger UI), "
            "this endpoint returns JSON with the generated download URL instead of redirect."
        ),
        responses={
            200: openapi.Response(
                "JSON response for API clients/Swagger",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "file_id": openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_UUID),
                        "download_url": openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_URI),
                    },
                ),
            ),
            302: "Redirect to presigned download URL",
            403: "Access denied",
            404: "Not found",
        },
    )
    def get(self, request, file_id):
        file_obj = get_object_or_404(FileAsset, id=file_id, deleted_at__isnull=True)
        principal = getattr(request, "user", None)
        if not _can_read(principal, file_obj):
            return Response({"error": {"code": "permission_denied", "message": "Access denied."}}, status=403)

        s3 = S3MultipartService()
        download_url = s3.presign_download_url(
            storage_key=file_obj.storage_key,
            mime_type=file_obj.mime_type,
            filename=file_obj.display_name or file_obj.original_name,
        )

        accept_header = request.META.get("HTTP_ACCEPT", "")
        if "application/json" in accept_header:
            return Response({"file_id": str(file_obj.id), "download_url": download_url})

        return HttpResponseRedirect(redirect_to=download_url)
