"""Isolated tests only; never configured by production."""
from .settings import *  # noqa: F403

DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
ALLOWED_HOSTS = ['testserver', 'localhost']
S3_ACCESS_KEY_ID = None
S3_SECRET_ACCESS_KEY = None
SSO_INTROSPECTION_CLIENT_ID = 'synthetic-inspector'
SSO_INTROSPECTION_CLIENT_SECRET = 'synthetic-only'
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
