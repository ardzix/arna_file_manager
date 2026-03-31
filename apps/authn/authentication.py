from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError
from rest_framework import authentication
from rest_framework.exceptions import AuthenticationFailed


@dataclass
class TokenPrincipal:
    user_id: str
    org_id: str | None
    org_name: str | None
    roles: list[str]
    permissions: list[str]
    is_owner: bool
    claims: dict[str, Any]

    @property
    def is_authenticated(self) -> bool:
        return True


class SSOJWTAuthentication(authentication.BaseAuthentication):
    def _read_public_key(self) -> str:
        key_path = Path(settings.PUBLIC_KEY_PATH)
        if not key_path.exists():
            raise AuthenticationFailed("Public key not configured.")
        return key_path.read_text(encoding="utf-8").strip()

    def authenticate(self, request):
        auth_header = authentication.get_authorization_header(request).decode("utf-8")
        if not auth_header:
            return None

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise AuthenticationFailed("Invalid authorization header format.")

        token = parts[1]
        public_key = self._read_public_key()
        try:
            payload = jwt.decode(
                token,
                public_key,
                algorithms=[settings.JWT_ALGORITHM],
                options={"verify_aud": False},
            )
        except ExpiredSignatureError as exc:
            raise AuthenticationFailed("Token expired.") from exc
        except JWTError as exc:
            raise AuthenticationFailed("Invalid token.") from exc

        if payload.get("token_type") != "access":
            raise AuthenticationFailed("Invalid token type.")

        user_id = payload.get("user_id")
        if not user_id:
            raise AuthenticationFailed("Missing user_id claim.")

        principal = TokenPrincipal(
            user_id=str(user_id),
            org_id=payload.get("org_id"),
            org_name=payload.get("org_name"),
            roles=payload.get("roles", []),
            permissions=payload.get("permissions", []),
            is_owner=bool(payload.get("is_owner", False)),
            claims=payload,
        )
        return principal, payload
