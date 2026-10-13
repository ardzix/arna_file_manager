"""Online revocation check against SSO. Credentials stay in this backend."""
from urllib.parse import urlsplit

import requests
from django.conf import settings
from rest_framework.exceptions import APIException, AuthenticationFailed


class SSOUnavailable(APIException):
    status_code = 503
    default_code = 'sso_unavailable'
    default_detail = 'SSO device verification is temporarily unavailable. Retry later.'


def introspect_device(raw, claims):
    base = settings.SSO_BASE_URL.rstrip('/')
    parsed = urlsplit(base)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or not settings.SSO_INTROSPECTION_CLIENT_ID or not settings.SSO_INTROSPECTION_CLIENT_SECRET):
        raise SSOUnavailable()
    try:
        auth = requests.post(base + '/api/auth/service-token/', json={
            'client_id': settings.SSO_INTROSPECTION_CLIENT_ID,
            'client_secret': settings.SSO_INTROSPECTION_CLIENT_SECRET, 'audience': 'arna-sso-devices'},
            timeout=5, allow_redirects=False)
        if auth.status_code != 200:
            raise SSOUnavailable()
        token = auth.json()['access']
        response = requests.post(base + '/api/v1/devices/introspect/', json={
            'access_token': raw, 'audience': settings.JWT_AUDIENCE},
            headers={'Authorization': f'Bearer {token}'}, timeout=5, allow_redirects=False)
        if response.status_code != 200:
            raise SSOUnavailable()
        data = response.json()
        if data.get('active') is not True:
            raise AuthenticationFailed('Device is expired, revoked, replaced or its SSO permissions changed.')
        checks = {'device_id': claims['device_id'], 'organization_id': claims['org_id'],
                  'tenant_id': claims['tenant_id'], 'credential_version': claims['credential_version'],
                  'audience': claims['aud'], 'permissions': claims['permissions'], 'scopes': claims['scopes']}
        if any(data.get(key) != value for key, value in checks.items()):
            raise AuthenticationFailed('SSO device context does not match this token.')
    except (requests.RequestException, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise SSOUnavailable() from exc
