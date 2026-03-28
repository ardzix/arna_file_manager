from django.contrib import admin

from .models import FileAsset, Folder, MultipartUpload, MultipartUploadPart


@admin.register(Folder)
class FolderAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "owner_scope", "owner_user_id", "owner_org_id", "created_at")
    search_fields = ("name", "owner_user_id", "owner_org_id")


@admin.register(FileAsset)
class FileAssetAdmin(admin.ModelAdmin):
    list_display = ("id", "display_name", "owner_scope", "visibility", "status", "created_at")
    list_filter = ("owner_scope", "visibility", "status")
    search_fields = ("display_name", "original_name", "owner_user_id", "owner_org_id")


@admin.register(MultipartUpload)
class MultipartUploadAdmin(admin.ModelAdmin):
    list_display = ("id", "file", "provider_upload_id", "status", "expires_at")
    list_filter = ("status",)
    search_fields = ("provider_upload_id",)


@admin.register(MultipartUploadPart)
class MultipartUploadPartAdmin(admin.ModelAdmin):
    list_display = ("id", "multipart_upload", "part_number", "etag", "uploaded_at")
    list_filter = ("uploaded_at",)
