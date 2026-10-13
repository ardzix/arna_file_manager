import base64
import hashlib
import json
import tempfile
import time
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

import jwt
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from django.conf import settings
from django.test import TestCase, override_settings
from rest_framework.test import APIClient


class ResourceAuthenticationTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.temp = tempfile.TemporaryDirectory(prefix='synthetic-fm-auth-')
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public = Path(cls.temp.name) / 'public.pem'
        public.write_bytes(cls.key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        cls.settings = override_settings(PUBLIC_KEY_PATH=public)
        cls.settings.enable()

    @classmethod
    def tearDownClass(cls):
        cls.settings.disable()
        cls.temp.cleanup()
        super().tearDownClass()

    def setUp(self):
        self.client = APIClient()
        self.device_id, self.org_id, self.tenant_id = map(str, (uuid.uuid4(), uuid.uuid4(), uuid.uuid4()))

    def claims(self, kind='device', **extra):
        data = {'iss': settings.JWT_ISSUER, 'aud': 'storage', 'exp': int(time.time()) + 300,
                'iat': int(time.time()), 'jti': str(uuid.uuid4()), 'principal_type': kind,
                'token_type': 'device' if kind == 'device' else 'access', 'org_id': self.org_id,
                'organization_id': self.org_id, 'tenant_id': self.tenant_id, 'is_owner': False,
                'roles': [], 'permissions': ['storage.files.read'], 'scopes': ['storage.files.read']}
        if kind == 'device':
            data.update(device_id=self.device_id, sub=self.device_id, credential_version=1, client_id='synthetic-device')
        elif kind == 'user':
            data['user_id'] = str(uuid.uuid4())
        else:
            data['service_id'] = str(uuid.uuid4())
        return {**data, **extra}

    def token(self, claims):
        return jwt.encode(claims, self.key, algorithm='RS256')

    def inspector(self, claims, **extra):
        data = {'active': True, 'device_id': claims['device_id'], 'organization_id': claims['org_id'],
                'tenant_id': claims['tenant_id'], 'credential_version': claims['credential_version'],
                'audience': claims['aud'], 'permissions': claims['permissions'], 'scopes': claims['scopes']}
        return patch('apps.authn.introspection.requests.post', side_effect=[
            Mock(status_code=200, json=Mock(return_value={'access': 'synthetic-service-token'})),
            Mock(status_code=200, json=Mock(return_value={**data, **extra}))])

    def get(self, claims):
        return self.client.get('/api/v1/files', HTTP_AUTHORIZATION='Bearer ' + self.token(claims))

    def test_same_permission_check_for_human_and_device(self):
        for kind in ('user', 'device'):
            claims = self.claims(kind)
            if kind == 'device':
                with self.inspector(claims) as calls:
                    response = self.get(claims)
                self.assertEqual(calls.call_count, 2)
                self.assertEqual(calls.call_args.kwargs['timeout'], 5)
                self.assertFalse(calls.call_args.kwargs['allow_redirects'])
            else:
                response = self.get(claims)
            self.assertEqual(response.status_code, 200, response.data)
            claims['permissions'] = claims['scopes'] = []
            if kind == 'device':
                with self.inspector(claims):
                    response = self.get(claims)
            else:
                response = self.get(claims)
            self.assertEqual(response.status_code, 403)
            self.assertIn('storage.files.read', response.data['detail'])
            self.assertEqual(response['X-Request-ID'], response.data['request_id'])

    def test_wrong_audience_issuer_type_and_missing_context_are_401(self):
        bad = [{'aud': 'photobooth-api'}, {'iss': 'https://attacker.test'}, {'token_type': 'access'},
               {'tenant_id': None}, {'organization_id': str(uuid.uuid4())}, {'is_owner': True},
               {'credential_version': '1'}, {'permissions': 'storage.files.read'}, {'exp': int(time.time()) - 100}]
        with patch('apps.authn.introspection.requests.post') as calls:
            for extra in bad:
                self.assertEqual(self.get(self.claims(**extra)).status_code, 401, extra)
            calls.assert_not_called()

    def test_revoked_and_changed_grants_are_401(self):
        claims = self.claims()
        for extra in ({'active': False}, {'permissions': []}, {'tenant_id': str(uuid.uuid4())}, {'credential_version': 2}):
            with self.inspector(claims, **extra):
                response = self.get(claims)
            self.assertEqual(response.status_code, 401)

    def test_downstream_failure_is_clear_503(self):
        with patch('apps.authn.introspection.requests.post', side_effect=requests.Timeout):
            response = self.get(self.claims())
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data['error'], 'sso_unavailable')

    def test_service_storage_token_retains_service_scope_contract(self):
        self.assertEqual(self.get(self.claims('service')).status_code, 200)
        self.assertEqual(self.get(self.claims('service', scopes=[])).status_code, 403)

    def test_resource_validates_dpop_signature_url_token_hash_and_replay(self):
        key = ec.generate_private_key(ec.SECP256R1())
        numbers = key.public_key().public_numbers()
        public = {'kty': 'EC', 'crv': 'P-256',
                  'x': base64.urlsafe_b64encode(numbers.x.to_bytes(32, 'big')).rstrip(b'=').decode(),
                  'y': base64.urlsafe_b64encode(numbers.y.to_bytes(32, 'big')).rstrip(b'=').decode()}
        thumb = base64.urlsafe_b64encode(hashlib.sha256(json.dumps(public, sort_keys=True, separators=(',', ':')).encode()).digest()).rstrip(b'=').decode()
        claims = self.claims(cnf={'jkt': thumb})
        raw = self.token(claims)
        proof = jwt.encode({'iat': int(time.time()), 'jti': str(uuid.uuid4()), 'htm': 'GET',
            'htu': settings.STORAGE_PUBLIC_BASE_URL + '/api/v1/files',
            'ath': base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest()).rstrip(b'=').decode()}, key,
            algorithm='ES256', headers={'typ': 'dpop+jwt', 'jwk': public})
        headers = {'HTTP_AUTHORIZATION': 'DPoP ' + raw, 'HTTP_DPOP': proof}
        with self.inspector(claims):
            response = self.client.get('/api/v1/files', **headers)
        self.assertEqual(response.status_code, 200, response.data)
        with self.inspector(claims):
            self.assertEqual(self.client.get('/api/v1/files', **headers).status_code, 400)
        with self.inspector(claims):
            self.assertEqual(self.get(claims).status_code, 401)
        with self.inspector(claims):
            self.assertEqual(self.client.get('/api/v1/files', HTTP_AUTHORIZATION='DPoP ' + raw).status_code, 400)
