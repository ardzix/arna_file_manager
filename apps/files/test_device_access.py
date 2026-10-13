import uuid
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient
from apps.authn.authentication import TokenPrincipal
from .models import FileAsset, FileStatus, Folder


class TenantDeviceFileTests(TestCase):
    def setUp(self):
        self.org, self.tenant, self.device = map(str, (uuid.uuid4(), uuid.uuid4(), uuid.uuid4()))
        self.principal = TokenPrincipal(principal_type='device', user_id=None, service_id=None, org_id=self.org,
            org_name='Synthetic', device_id=self.device, tenant_id=self.tenant, roles=[],
            permissions=['storage.files.create', 'storage.files.read', 'storage.files.update', 'storage.files.delete',
                         'storage.files.share', 'storage.folders.create'], scopes=[], is_owner=False, claims={})
        self.client = APIClient()
        self.client.force_authenticate(user=self.principal)

    def upload(self, **extra):
        return self.client.post('/api/v1/files/upload', {'filename': 'tenant.jpg', 'size_bytes': 100, **extra}, format='json')

    def test_device_upload_complete_read_share_and_audit_are_tenant_owned(self):
        folder = self.client.post('/api/v1/folders', {'name': 'Device photos'}, format='json')
        self.assertEqual(folder.status_code, 201, folder.data)
        response = self.upload(folder_id=folder.data['id'], org_id=str(uuid.uuid4()), tenant_id=str(uuid.uuid4()))
        self.assertEqual(response.status_code, 201, response.data)
        file = FileAsset.objects.get(pk=response.data['file_id'])
        self.assertEqual(str(file.owner_org_id), self.org)
        self.assertEqual(str(file.owner_tenant_id), self.tenant)
        self.assertEqual(str(file.created_by_device_id), self.device)
        self.assertIsNone(file.owner_user_id)
        path = f'/api/v1/files/{file.pk}'
        self.assertEqual(self.client.post(path + '/parts/presign', {'parts': [1]}, format='json').status_code, 200)
        self.assertEqual(self.client.post(path + '/complete', {'parts': [{'part_number': 1, 'etag': 'synthetic'}]}, format='json').status_code, 200)
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.get(f'/{file.pk}', HTTP_ACCEPT='application/json').status_code, 200)
        shared = self.client.post(path + '/shares', {}, format='json')
        self.assertEqual(shared.status_code, 201)
        self.assertEqual(str(file.shares.get().created_by_device_id), self.device)
        self.assertEqual(self.client.delete(path + '/shares/' + shared.data['share_id']).status_code, 204)

    def test_human_and_device_read_the_same_tenant_files(self):
        response = self.upload()
        file_id = response.data['file_id']
        self.principal.principal_type = 'user'
        self.principal.user_id = str(uuid.uuid4())
        self.principal.device_id = None
        response = self.client.get('/api/v1/files')
        self.assertEqual([file['id'] for file in response.data], [file_id])

    def test_missing_grants_deny_every_upload_step_and_mutation(self):
        file_id = self.upload().data['file_id']
        self.principal.permissions = []
        path = f'/api/v1/files/{file_id}'
        operations = [('get', path, None), ('patch', path, {'display_name': 'Blocked'}), ('delete', path, None),
                      ('post', path + '/parts/presign', {'parts': [1]}), ('post', path + '/complete', {'parts': []}),
                      ('post', path + '/abort', {}), ('post', path + '/move', {'folder_id': str(uuid.uuid4())}),
                      ('post', path + '/shares', {}), ('delete', path + '/shares/' + str(uuid.uuid4()), None),
                      ('post', '/api/v1/folders', {'name': 'Blocked'}), ('get', '/api/v1/folders/root/children', None)]
        for method, url, data in operations:
            with self.subTest(method=method, url=url):
                result = getattr(self.client, method)(url, data, format='json')
                self.assertEqual(result.status_code, 403, result.data)
        self.assertEqual(FileAsset.objects.get(pk=file_id).display_name, 'tenant.jpg')

    def test_cross_org_and_same_org_other_tenant_are_hidden_from_all_operations(self):
        file_id = self.upload().data['file_id']
        path = f'/api/v1/files/{file_id}'
        for field in ('org_id', 'tenant_id'):
            previous = getattr(self.principal, field)
            setattr(self.principal, field, str(uuid.uuid4()))
            self.assertEqual(self.client.get('/api/v1/files').data, [])
            for method, suffix, data in [('get', '', None), ('patch', '', {'display_name': 'Blocked'}),
                                         ('delete', '', None), ('post', '/parts/presign', {'parts': [1]}),
                                         ('post', '/complete', {'parts': []}), ('post', '/abort', {}),
                                         ('post', '/shares', {})]:
                self.assertEqual(getattr(self.client, method)(path + suffix, data, format='json').status_code, 404)
            setattr(self.principal, field, previous)

    def test_legacy_org_files_are_not_implicitly_assigned_to_device_tenant(self):
        file_id = self.upload().data['file_id']
        FileAsset.objects.filter(pk=file_id).update(owner_tenant_id=None)
        self.assertEqual(self.client.get('/api/v1/files').data, [])
        self.assertEqual(self.client.get(f'/api/v1/files/{file_id}').status_code, 404)

    def test_parent_and_upload_folder_cannot_cross_tenant_or_ownership_scope(self):
        other = Folder.objects.create(name='Other tenant', owner_scope='org', owner_org_id=self.org,
            owner_tenant_id=uuid.uuid4(), created_by_user_id=uuid.uuid4())
        with patch('apps.files.views.S3MultipartService.initiate_multipart_upload') as s3:
            self.assertEqual(self.upload(folder_id=str(other.pk)).status_code, 404)
            s3.assert_not_called()
        self.assertEqual(self.client.post('/api/v1/folders', {'name': 'Escape', 'parent': str(other.pk)}, format='json').status_code, 403)
        self.assertEqual(self.client.get(f'/api/v1/folders/{other.pk}/children').status_code, 404)

    def test_create_permission_does_not_implicitly_allow_publication_or_personal_files(self):
        self.principal.permissions = ['storage.files.create']
        self.assertEqual(self.upload(visibility='public').status_code, 403)
        self.assertEqual(self.upload(owner_scope='user').status_code, 400)
        self.assertEqual(self.upload(owner_scope='service').status_code, 400)
        self.assertFalse(FileAsset.objects.exists())

    def test_invalid_folder_filter_returns_400_instead_of_500(self):
        self.assertEqual(self.client.get('/api/v1/files', {'folder_id': 'not-uuid'}).status_code, 400)
