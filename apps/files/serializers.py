from rest_framework import serializers

from .models import FileAsset, FileStatus, Folder, OwnerScope, Visibility


class UploadInitiateSerializer(serializers.Serializer):
    filename = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    size_bytes = serializers.IntegerField(min_value=1)
    mime_type = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    owner_scope = serializers.ChoiceField(choices=OwnerScope.choices, required=False, default=OwnerScope.USER)
    visibility = serializers.ChoiceField(choices=Visibility.choices, required=False, default=Visibility.PRIVATE)
    folder_id = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, attrs):
        filename = (attrs.get("filename") or "").strip()
        mime_type = (attrs.get("mime_type") or "").strip()
        attrs["filename"] = filename or "unnamed-file"
        attrs["mime_type"] = mime_type or "application/octet-stream"

        owner_scope = attrs["owner_scope"]
        visibility = attrs["visibility"]
        request = self.context["request"]
        principal = request.user

        if owner_scope == OwnerScope.ORG and not principal.org_id:
            raise serializers.ValidationError("JWT does not include org_id for org owner scope.")
        if visibility == Visibility.ORG and owner_scope != OwnerScope.ORG:
            raise serializers.ValidationError("org visibility requires owner_scope=org.")
        return attrs


class PresignPartsSerializer(serializers.Serializer):
    parts = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=False)


class CompleteUploadPartSerializer(serializers.Serializer):
    part_number = serializers.IntegerField(min_value=1)
    etag = serializers.CharField(max_length=255)


class CompleteUploadSerializer(serializers.Serializer):
    parts = CompleteUploadPartSerializer(many=True)

    def validate_parts(self, parts):
        numbers = [item["part_number"] for item in parts]
        if len(numbers) != len(set(numbers)):
            raise serializers.ValidationError("Duplicate part_number is not allowed.")
        return sorted(parts, key=lambda item: item["part_number"])


class FileSerializer(serializers.ModelSerializer):
    url = serializers.CharField(source="stable_url", read_only=True)
    folder_id = serializers.UUIDField(source="folder.id", read_only=True, allow_null=True)

    class Meta:
        model = FileAsset
        fields = [
            "id",
            "url",
            "display_name",
            "original_name",
            "mime_type",
            "size_bytes",
            "owner_scope",
            "owner_user_id",
            "owner_org_id",
            "visibility",
            "status",
            "folder_id",
            "created_at",
            "updated_at",
        ]


class FileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = FileAsset
        fields = ["display_name", "visibility"]

    def validate_visibility(self, value):
        file_obj: FileAsset = self.instance
        if value == Visibility.ORG and file_obj.owner_scope != OwnerScope.ORG:
            raise serializers.ValidationError("org visibility requires owner_scope=org.")
        return value


class FileMoveSerializer(serializers.Serializer):
    folder_id = serializers.UUIDField()


class FolderCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Folder
        fields = ["id", "name", "parent", "owner_scope", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
