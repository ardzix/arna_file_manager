import base64
import hashlib
import json
import secrets
import time
from datetime import timedelta
import jwt
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from .models import DeviceProofReplay

def _b64hash(value):
    return base64.urlsafe_b64encode(hashlib.sha256(value).digest()).rstrip(b"=").decode()


def verify_dpop(request, expected_thumbprint="", access_token=None):
    proof = request.headers.get("DPoP", "")
    if not proof:
        if expected_thumbprint:
            raise ValidationError({"DPoP": "A proof from the registered device key is required."})
        return ""
    try:
        if len(proof) > 8192:
            raise ValueError("Oversized proof")
        header = jwt.get_unverified_header(proof)
        jwk = header["jwk"]
        alg = header["alg"]
        if header.get("typ") != "dpop+jwt" or alg not in {"RS256", "ES256"} or header.get("crit"):
            raise ValueError("Unsupported proof")
        if not isinstance(jwk, dict) or any(key in jwk for key in ("d", "p", "q", "dp", "dq", "qi", "oth", "k")):
            raise ValueError("Public asymmetric key required")
        if alg == "RS256" and jwk.get("kty") == "RSA":
            public = {key: jwk[key] for key in ("e", "kty", "n")}
        elif alg == "ES256" and jwk.get("kty") == "EC" and jwk.get("crv") == "P-256":
            public = {key: jwk[key] for key in ("crv", "kty", "x", "y")}
        else:
            raise ValueError("Key/algorithm mismatch")
        key = jwt.PyJWK.from_dict(public, algorithm=alg).key
        if alg == "RS256" and key.key_size < 2048:
            raise ValueError("Weak key")
        thumbprint = _b64hash(json.dumps(public, sort_keys=True, separators=(",", ":")).encode())
        if expected_thumbprint and not secrets.compare_digest(expected_thumbprint, thumbprint):
            raise ValueError("Wrong key")
        claims = jwt.decode(proof, key, algorithms=[alg], leeway=30,
                            options={"verify_aud": False, "require": ["iat", "jti", "htm", "htu"]})
        # Fixed trusted origin avoids proxy Host headers changing the proof target.
        expected_uri = settings.STORAGE_PUBLIC_BASE_URL.rstrip("/") + request.path
        if (claims["htm"] != request.method or claims["htu"] != expected_uri
                or type(claims["iat"]) is not int or not -30 <= time.time() - claims["iat"] <= 120
                or not isinstance(claims["jti"], str) or not 1 <= len(claims["jti"]) <= 200):
            raise ValueError("Invalid proof claims")
        if access_token is not None and not secrets.compare_digest(str(claims.get("ath", "")), _b64hash(access_token.encode())):
            raise ValueError("Access token hash mismatch")
    except (jwt.PyJWTError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise ValidationError({"DPoP": "Invalid proof: check signature, key, method, URL, timestamp and token hash."}) from exc
    proof_hash = hashlib.sha256((thumbprint + "\n" + claims["jti"]).encode()).hexdigest()
    try:
        with transaction.atomic():
            DeviceProofReplay.objects.filter(expires_at__lte=timezone.now()).delete()
            DeviceProofReplay.objects.create(proof_hash=proof_hash, expires_at=timezone.now() + timedelta(minutes=5))
    except IntegrityError as exc:
        raise ValidationError({"DPoP": "This proof has already been used. Send a fresh proof."}) from exc
    return thumbprint
