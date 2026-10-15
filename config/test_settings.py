"""Isolated tests only; never configured by production."""
from .settings import *  # noqa: F403
import os

DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
if os.getenv('STORAGE_TEST_POSTGRES_HOST'):
    DATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql', 'NAME': 'storage_device_isolated',
        'USER': 'postgres', 'PASSWORD': os.environ['STORAGE_TEST_POSTGRES_PASSWORD'],
        'HOST': os.environ['STORAGE_TEST_POSTGRES_HOST'], 'PORT': '5432', 'OPTIONS': {'connect_timeout': 5}}}
ALLOWED_HOSTS = ['testserver', 'localhost']
S3_ACCESS_KEY_ID = None
S3_SECRET_ACCESS_KEY = None
SSO_INTROSPECTION_CLIENT_ID = 'synthetic-inspector'
SSO_INTROSPECTION_CLIENT_SECRET = 'synthetic-only'
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
