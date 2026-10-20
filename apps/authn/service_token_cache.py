"""Cache only backend credentials, never device status or effective grants."""
import hashlib
import threading
import time

_lock = threading.Lock()
_tokens = {}


def cache_key(base, client_id, secret):
    return base, client_id, hashlib.sha256(secret.encode()).hexdigest()


def service_token(key, fetch):
    with _lock:
        now = time.monotonic()
        cached = _tokens.get(key)
        if cached and cached[1] > now:
            return cached[0]
        _tokens.pop(key, None)
        reply = fetch()
        token = reply['access']
        if not isinstance(token, str) or not token:
            raise ValueError('Invalid backend token response')
        lifetime = reply.get('expires_in')
        # expires_in is from the authenticated HTTPS response, not decoded JWT data.
        if type(lifetime) is int and lifetime > 30:
            if len(_tokens) >= 8:
                _tokens.clear()
            _tokens[key] = token, now + min(lifetime, 300) - 30
        return token


def invalidate(key, rejected_token):
    with _lock:
        if _tokens.get(key, (None,))[0] == rejected_token:
            _tokens.pop(key, None)
