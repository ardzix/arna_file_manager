import uuid

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.authn.authentication import TokenPrincipal
from apps.files.models import FileAsset, FileStatus, OwnerScope, Visibility


class ServiceOwnedShareTests(TestCase):
    def setUp(self):
        self.service_id = str(uuid.uuid4())
        self.principal = TokenPrincipal(
            principal_type="service",
            user_id=None,
            service_id=self.service_id,
            org_id=None,
            org_name=None,
            roles=[],
            permissions=[],
            scopes=["storage.files.create", "storage.files.share"],
            is_owner=False,
            claims={},
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.principal)

    def test_service_creates_owned_file_and_shared_link(self):
        response = self.client.post(
            "/api/files/upload",
            {
                "filename": "candidate.pdf",
                "size_bytes": 100,
                "mime_type": "application/pdf",
                "owner_scope": "service",
                "visibility": "shared",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        file_obj = FileAsset.objects.get(id=response.data["file_id"])
        self.assertEqual(file_obj.owner_scope, OwnerScope.SERVICE)
        self.assertEqual(str(file_obj.owner_service_id), self.service_id)
        file_obj.status = FileStatus.ACTIVE
        file_obj.completed_at = timezone.now()
        file_obj.save()

        shared = self.client.post(f"/api/files/{file_obj.id}/shares", {"expires_in_days": 30}, format="json")

        self.assertEqual(shared.status_code, 201)
        self.assertEqual(file_obj.shares.count(), 1)
        self.assertTrue(shared.data["url"].startswith("https://storage.arnatech.id/s/"))
        token = shared.data["url"].rsplit("/", 1)[-1]
        resolved = APIClient().get(f"/s/{token}")
        self.assertEqual(resolved.status_code, 302)

    def test_service_requires_create_scope(self):
        self.principal.scopes = []
        response = self.client.post(
            "/api/files/upload",
            {"filename": "candidate.pdf", "size_bytes": 100, "owner_scope": "service"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
