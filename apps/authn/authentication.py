from dataclasses import dataclass
from pathlib import Path
from typing import Any
import uuid

import jwt
from django.conf import settings
from rest_framework import authentication
from rest_framework.exceptions import AuthenticationFailed

from .introspection import introspect_device
from .proofs import verify_dpop


@dataclass
class TokenPrincipal:
    principal_type: str
    user_id: str | None
    service_id: str | None
    org_id: str | None
    org_name: str | None
    roles: list[str]
    permissions: list[str]
    scopes: list[str]
    is_owner: bool
    claims: dict[str, Any]
    tenant_id: str | None = None
    device_id: str | None = None

    @property
    def is_authenticated(self) -> bool:
        return True


class SSOJWTAuthentication(authentication.BaseAuthentication):
    def authenticate_header(self, request):
        return 'Bearer'

    def _read_public_key(self) -> str:
        path = Path(settings.PUBLIC_KEY_PATH)
        if not path.is_file():
            raise AuthenticationFailed('SSO public key is not configured.')
        return path.read_text(encoding='utf-8').strip()

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).split()
        if not header:
            return None
        try:
            if len(header) != 2 or header[0].lower() not in {b'bearer', b'dpop'}:
                raise ValueError('Invalid authorization header')
            raw = header[1].decode('ascii')
            payload = jwt.decode(raw, self._read_public_key(), algorithms=['RS256'],
                                 issuer=settings.JWT_ISSUER, audience=settings.JWT_AUDIENCE,
                                 options={'require': ['iss', 'aud', 'exp', 'iat', 'jti', 'token_type']})
            kind = payload.get('principal_type', 'user')
            token_type = payload['token_type']
            if payload['aud'] != settings.JWT_AUDIENCE or kind not in {'user', 'device', 'service'}:
                raise ValueError('Wrong resource or principal type')
            if token_type != ('device' if kind == 'device' else 'access') and not (kind == 'service' and token_type == 'service'):
                raise ValueError('Wrong token type')
            identity = payload['device_id' if kind == 'device' else 'service_id' if kind == 'service' else 'user_id']
            uuid.UUID(identity)
            for field in ('org_id', 'tenant_id'):
                if payload.get(field) is not None:
                    uuid.UUID(payload[field])
            for field in ('permissions', 'scopes', 'roles'):
                if not isinstance(payload.get(field, []), list) or any(not isinstance(v, str) for v in payload.get(field, [])):
                    raise ValueError('Invalid permission claims')
            if kind == 'device':
                if (not payload.get('org_id') or not payload.get('tenant_id')
                        or payload.get('organization_id') != payload['org_id'] or payload.get('sub') != identity
                        or type(payload.get('credential_version')) is not int
                        or payload.get('is_owner') is not False or payload.get('permissions') != payload.get('scopes')):
                    raise ValueError('Incomplete device context')
                introspect_device(raw, payload)
                thumbprint = (payload.get('cnf') or {}).get('jkt', '')
                if header[0].lower() != (b'dpop' if thumbprint else b'bearer'):
                    raise ValueError('Wrong device proof scheme')
                verify_dpop(request, thumbprint, access_token=raw)
            elif header[0].lower() != b'bearer':
                raise ValueError('Bearer authorization required')
        except (jwt.PyJWTError, ValueError, TypeError, KeyError, AttributeError) as exc:
            raise AuthenticationFailed('Invalid SSO token: check issuer, storage audience, expiry, identity and context.') from exc
        return TokenPrincipal(
            principal_type=kind, user_id=payload.get('user_id') if kind == 'user' else None,
            service_id=payload.get('service_id') if kind == 'service' else None,
            device_id=payload.get('device_id') if kind == 'device' else None,
            org_id=payload.get('org_id'), org_name=payload.get('org_name'), tenant_id=payload.get('tenant_id'),
            roles=payload.get('roles', []), permissions=payload.get('permissions', []), scopes=payload.get('scopes', []),
            is_owner=kind == 'user' and payload.get('is_owner') is True, claims=payload), payload
