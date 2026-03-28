from pathlib import Path
from decouple import config


BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config("SECRET_KEY", default="dev-only-secret-key")
DEBUG = config("DEBUG", default=True, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "drf_yasg",
    "apps.authn",
    "apps.files",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": config("DB_ENGINE", default="django.db.backends.postgresql"),
        "NAME": config("DB_NAME", default="file_manager"),
        "USER": config("DB_USER", default="postgres"),
        "PASSWORD": config("DB_PASSWORD", default="postgres"),
        "HOST": config("DB_HOST", default="localhost"),
        "PORT": config("DB_PORT", default="5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "id-id"
TIME_ZONE = "Asia/Jakarta"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "static"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.authn.authentication.SSOJWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ],
    "EXCEPTION_HANDLER": "rest_framework.views.exception_handler",
}

SWAGGER_SETTINGS = {
    "SECURITY_DEFINITIONS": {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": "Bearer token from ArnaTech SSO. Format: Bearer <access_token>",
        }
    },
    "USE_SESSION_AUTH": False,
    "JSON_EDITOR": True,
    "SUPPORTED_SUBMIT_METHODS": ["get", "post", "put", "delete", "patch"],
    "OPERATIONS_SORTER": "alpha",
    "TAGS_SORTER": "alpha",
    "DOC_EXPANSION": "list",
    "DEEP_LINKING": True,
    "SHOW_REQUEST_HEADERS": True,
    "VALIDATOR_URL": None,
}

CORS_ALLOW_ALL_ORIGINS = config("CORS_ALLOW_ALL_ORIGINS", default=True, cast=bool)
CORS_ALLOW_CREDENTIALS = True

PUBLIC_KEY_PATH = Path(config("PUBLIC_KEY_PATH", default=str(BASE_DIR / "public.pem")))
JWT_ALGORITHM = config("JWT_ALGORITHM", default="RS256")

STORAGE_PUBLIC_BASE_URL = config("STORAGE_PUBLIC_BASE_URL", default="https://storage.arnatech.id")
S3_ENDPOINT_URL = config("S3_ENDPOINT_URL", default=None)
S3_REGION_NAME = config("S3_REGION_NAME", default="us-east-1")
S3_ACCESS_KEY_ID = config("S3_ACCESS_KEY_ID", default=None)
S3_SECRET_ACCESS_KEY = config("S3_SECRET_ACCESS_KEY", default=None)
S3_BUCKET_NAME = config("S3_BUCKET_NAME", default="arnatech-files")
S3_PRESIGN_EXPIRES_SECONDS = config("S3_PRESIGN_EXPIRES_SECONDS", default=900, cast=int)
S3_DEFAULT_PART_SIZE_BYTES = config("S3_DEFAULT_PART_SIZE_BYTES", default=8 * 1024 * 1024, cast=int)

MAX_UPLOAD_SIZE_MB = config("MAX_UPLOAD_SIZE_MB", default=1024, cast=int)
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE_MB * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE_MB * 1024 * 1024
