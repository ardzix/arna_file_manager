"""Run auth/file contracts with synthetic keys and isolated storage/database."""
import os
from pathlib import Path
import sys
import tempfile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    with tempfile.TemporaryDirectory(prefix='file-manager-contract-') as directory:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public = Path(directory) / 'public.pem'
        public.write_bytes(key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        os.environ.update(DJANGO_SETTINGS_MODULE='config.test_settings',
                          SECRET_KEY='synthetic-isolated-test', PUBLIC_KEY_PATH=str(public),
                          JWT_ISSUER='https://sso.arnatech.id', JWT_AUDIENCE='storage',
                          SSO_BASE_URL='https://sso.arnatech.id',
                          STORAGE_PUBLIC_BASE_URL='https://storage.arnatech.id',
                          S3_ACCESS_KEY_ID='', S3_SECRET_ACCESS_KEY='', DEBUG='true')
        import django
        django.setup()
        from django.core.management import call_command
        call_command('check')
        call_command('makemigrations', check=True, dry_run=True)
        call_command('test', 'apps.authn', 'apps.files', verbosity=2)


if __name__ == '__main__':
    main()
