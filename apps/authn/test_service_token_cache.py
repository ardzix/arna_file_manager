from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch
from django.test import SimpleTestCase
from rest_framework.exceptions import AuthenticationFailed
from apps.authn import service_token_cache as tokens
from apps.authn.introspection import introspect_device


class InspectorTokenCacheTests(SimpleTestCase):
    def setUp(self):
        tokens._tokens.clear()
        self.addCleanup(tokens._tokens.clear)
        self.claims = {'device_id': 'd', 'org_id': 'o', 'tenant_id': 't', 'credential_version': 1,
                       'aud': 'storage', 'permissions': ['storage.files.read'], 'scopes': ['storage.files.read']}
        self.active = {'active': True, 'device_id': 'd', 'organization_id': 'o', 'tenant_id': 't',
                       'credential_version': 1, 'audience': 'storage', 'permissions': ['storage.files.read'], 'scopes': ['storage.files.read']}

    def test_many_device_requests_reuse_service_jwt_but_revocation_is_fresh(self):
        active = dict(self.active)
        def request(url, **kwargs):
            data = {'access': 'synthetic-inspector', 'expires_in': 300} if url.endswith('service-token/') else dict(active)
            return Mock(status_code=200, json=Mock(return_value=data))
        with patch('apps.authn.introspection.requests.post', side_effect=request) as calls:
            for _ in range(20): introspect_device('device-token', self.claims)
            active['active'] = False
            with self.assertRaises(AuthenticationFailed): introspect_device('device-token', self.claims)
        self.assertEqual(sum(c.args[0].endswith('service-token/') for c in calls.call_args_list), 1)
        self.assertEqual(sum(c.args[0].endswith('introspect/') for c in calls.call_args_list), 21)

    def test_rejected_backend_token_is_refreshed_once(self):
        replies = [Mock(status_code=200, json=Mock(return_value={'access': 'old', 'expires_in': 300})),
                   Mock(status_code=401), Mock(status_code=200, json=Mock(return_value={'access': 'new', 'expires_in': 300})),
                   Mock(status_code=200, json=Mock(return_value=self.active))]
        with patch('apps.authn.introspection.requests.post', side_effect=replies) as calls:
            introspect_device('device-token', self.claims)
        self.assertEqual(calls.call_count, 4)
        self.assertEqual(calls.call_args.kwargs['headers']['Authorization'], 'Bearer new')

    def test_expiry_rotation_and_parallel_fetch(self):
        fetch = Mock(return_value={'access': 'backend-token', 'expires_in': 300})
        key = tokens.cache_key('https://sso.test', 'client', 'secret')
        with patch('apps.authn.service_token_cache.time.monotonic', return_value=100):
            with ThreadPoolExecutor(max_workers=8) as pool:
                self.assertEqual(list(pool.map(lambda _: tokens.service_token(key, fetch), range(20))), ['backend-token'] * 20)
        self.assertEqual(fetch.call_count, 1)
        with patch('apps.authn.service_token_cache.time.monotonic', return_value=371): tokens.service_token(key, fetch)
        tokens.service_token(tokens.cache_key('https://sso.test', 'client', 'rotated-secret'), fetch)
        self.assertEqual(fetch.call_count, 3)
        self.assertNotIn('secret', key)
