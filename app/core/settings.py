import os
import pathlib
import traceback
import types
import typing

import boto3
import corsheaders.defaults
import environ
import sentry_sdk
import sentry_sdk.integrations.aws_lambda
import sentry_sdk.integrations.django

if typing.TYPE_CHECKING:
    import mypy_boto3_ssm

is_aws_lambda = os.environ.get("AWS_LAMBDA_FUNCTION_NAME") is not None
if is_aws_lambda and (project_name := os.environ.get("PROJECT_NAME")) and (stage := os.environ.get("API_STAGE")):
    print("Running in AWS Lambda environment. Trying to load environment variables from AWS SSM Parameter Store.")
    try:
        ssm_client: "mypy_boto3_ssm.SSMClient" = boto3.client("ssm")
        next_token = ""  # nosec: B105
        while next_token is not None:
            result = ssm_client.get_parameters_by_path(
                Path=f"/{project_name}/{stage}",
                MaxResults=10,
                **({"NextToken": next_token} if next_token else {}),
            )
            os.environ.update({p["Name"].split("/")[-1]: p["Value"] for p in result["Parameters"]})
            next_token = result.get("NextToken")
        print("Successfully loaded environment variables from AWS SSM Parameter Store.")
    except Exception as e:
        print(
            "Failed to load environment variables from AWS SSM Parameter Store. Traceback: \n"
            + "".join(traceback.format_exception(e))
        )

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = pathlib.Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    IS_LOCAL=(bool, False),
    LOG_LEVEL=(str, "DEBUG"),
)
env.read_env(env.str("ENV_PATH", default="envfile/.env.local"))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

SECRET_KEY = env("DJANGO_SECRET_KEY", default="local_secret_key")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env("DEBUG")
IS_LOCAL = env("IS_LOCAL")

DEPLOYMENT_RELEASE_VERSION = os.environ.get("DEPLOYMENT_RELEASE_VERSION", "unknown")
# Loggers
SLACK = types.SimpleNamespace(token=env("SLACK_LOG_TOKEN", default=""), channel=env("SLACK_LOG_CHANNEL", default=""))

LOG_LEVEL = env("LOG_LEVEL")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "basic": {"format": "%(asctime)s:%(module)s:%(levelname)s:%(message)s", "datefmt": "%Y-%m-%d %H:%M:%S"},
        "slack": {"()": "core.logger.formatter.slack.SlackJsonFormatter"},
        "cloudwatch": {"()": "core.logger.formatter.cloudwatch.CloudWatchJsonFormatter"},
    },
    "handlers": {
        "console": {
            "level": LOG_LEVEL,
            "class": "logging.StreamHandler",
            "formatter": "basic",
        },
        "cloudwatch": {
            "level": LOG_LEVEL,
            "class": "logging.StreamHandler",
            "formatter": "cloudwatch",
        },
        "slack": {
            "level": LOG_LEVEL,
            "class": "core.logger.handler.slack.SlackHandler",
            "formatter": "slack",
        },
    },
    "loggers": {
        "django.db.backends": ({"level": LOG_LEVEL, "handlers": ["console"]} if IS_LOCAL else {}),
        "cloudwatch_logger": {"level": LOG_LEVEL, "handlers": ["cloudwatch"], "propagate": True},
        "slack_logger": ({"level": LOG_LEVEL, "handlers": ["slack"]} if SLACK.token and SLACK.channel else {}),
    },
}

# Zappa Settings
API_STAGE = env("API_STAGE", default="prod")
ADDITIONAL_TEXT_MIMETYPES: list[str] = []
ASYNC_RESPONSE_TABLE = ""
AWS_BOT_EVENT_MAPPING: dict[str, str] = {}
AWS_EVENT_MAPPING: dict[str, str] = {}
BASE_PATH = None
BINARY_SUPPORT = True
COGNITO_TRIGGER_MAPPING: dict[str, str] = {}
CONTEXT_HEADER_MAPPINGS: dict[str, str] = {}
DJANGO_SETTINGS = "core.settings"
DOMAIN = None
ENVIRONMENT_VARIABLES: dict[str, str] = {}
EXCEPTION_HANDLER = None
PROJECT_NAME = "PyConKR-backend"

ALLOWED_HOSTS = ["*"]

# CORS Settings
# pycon domain regex pattern
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^(http|https):\/\/([a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*\.pycon\.kr)$",  # pycon.kr 하위 도메인
    r"^(http|https):\/\/(localhost|127\.\d{1,3}\.\d{1,3}\.\d{1,3})(:\d{1,5})?$",  # 로컬 환경
]
CORS_ALLOWED_ORIGINS = [
    f"{protocol}://{domain}{port}"
    for protocol in ("http", "https")
    for domain in ("localhost", "127.0.0.1", "pycon.kr", "local.dev.pycon.kr")
    for port in ("", ":3000", ":5173")
]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [*corsheaders.defaults.default_headers, "accept-encoding", "origin", "x-csrftoken"]
SECURE_CROSS_ORIGIN_OPENER_POLICY = None if DEBUG else "same-origin"

# Application definition

INSTALLED_APPS = [
    # django model translation
    # https://django-modeltranslation.readthedocs.io/en/latest/installation.html#installed-apps
    "modeltranslation",
    # django default apps
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # CORS
    "corsheaders",
    # django-rest-framework
    "rest_framework",
    "rest_framework.authtoken",
    "drf_spectacular",
    "drf_standardized_errors",
    # django-filter
    "django_filters",
    # simple-history
    "simple_history",
    # zappa
    "zappa_django_utils",
    # For Shell Plus
    "django_extensions",
    # django-app
    "user",
    "file",
    "cms",
    # django-constance
    "constance",
]

MIDDLEWARE = [
    # Django default middlewares
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    # CORS
    "corsheaders.middleware.CorsMiddleware",
    # simple-history
    "simple_history.middleware.HistoryRequestMiddleware",
    # Request Response Logger
    "core.middleware.request_response_logger.RequestResponseLogger",
]

ROOT_URLCONF = "core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": ["core/templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.request",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": env("DATABASE_ENGINE", default="django.db.backends.sqlite3"),
        "NAME": env("DATABASE_NAME", default=str(BASE_DIR / "db.sqlite3")),
        "PORT": env("DATABASE_PORT", default=None),
        "HOST": env("DATABASE_HOST", default=None),
        "USER": env("DATABASE_USER", default=None),
        "PASSWORD": env("DATABASE_PASSWORD", default=None),
    },
}


# Constance Settings
CONSTANCE_BACKEND = "constance.backends.database.DatabaseBackend"
CONSTANCE_CONFIG: dict[str, tuple[int, str]] = {
    "DEBUG_COLLECT_SESSION_DATA": (False, "디버깅용 - 세션 데이터 수집 여부"),
}


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = "ko-kr"

TIME_ZONE = "Asia/Seoul"

USE_I18N = True

USE_TZ = True

MODELTRANSLATION_DEFAULT_LANGUAGE = "ko"

MODELTRANSLATION_LANGUAGES = ("ko", "en")

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/
STATIC_ROOT = BASE_DIR / "static"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_STORAGE_BACKEND = env("DJANGO_DEFAULT_STORAGE_BACKEND", default="storages.backends.s3.S3Storage")
STATIC_STORAGE_BACKEND = env("DJANGO_STATIC_STORAGE_BACKEND", default="storages.backends.s3.S3Storage")

PRIVATE_STORAGE_BUCKET_NAME = f"pyconkr-backend-{API_STAGE}"
PUBLIC_STORAGE_BUCKET_NAME = f"pyconkr-backend-{API_STAGE}-public"

STATIC_URL = (
    f"https://s3.ap-northeast-2.amazonaws.com/{PRIVATE_STORAGE_BUCKET_NAME}/"
    if STATIC_STORAGE_BACKEND == "storages.backends.s3.S3Storage"
    else "static/"
)
MEDIA_URL = (
    f"https://s3.ap-northeast-2.amazonaws.com/{PUBLIC_STORAGE_BUCKET_NAME}/"
    if DEFAULT_STORAGE_BACKEND == "storages.backends.s3.S3Storage"
    else "media/"
)

STATIC_STORAGE_OPTIONS = (
    {
        "bucket_name": PRIVATE_STORAGE_BUCKET_NAME,
        "file_overwrite": False,
        "addressing_style": "path",
    }
    if DEFAULT_STORAGE_BACKEND == "storages.backends.s3.S3Storage"
    else {}
)
PUBLIC_STORAGE_OPTIONS = (
    {
        "bucket_name": PRIVATE_STORAGE_BUCKET_NAME,
        "file_overwrite": False,
        "addressing_style": "path",
    }
    if DEFAULT_STORAGE_BACKEND == "storages.backends.s3.S3Storage"
    else {}
)
STORAGES = {
    "default": {"BACKEND": DEFAULT_STORAGE_BACKEND, "OPTIONS": STATIC_STORAGE_OPTIONS},
    "staticfiles": {"BACKEND": STATIC_STORAGE_BACKEND, "OPTIONS": STATIC_STORAGE_OPTIONS},
    "public": {"BACKEND": DEFAULT_STORAGE_BACKEND, "OPTIONS": PUBLIC_STORAGE_OPTIONS},
}

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "core.fields.UUIDAutoField"

AUTH_USER_MODEL = "user.UserExt"

# Cookies
# https://docs.djangoproject.com/en/5.2/ref/settings/#cookies
COOKIE_PREFIX = (("LOCAL_" if IS_LOCAL else "DEBUG_") if DEBUG else "") + "PYCONKR_BACKEND_"
COOKIE_SAMESITE = "Lax" if IS_LOCAL else "None"
COOKIE_SECURE = not IS_LOCAL
COOKIE_HTTPONLY = True
COOKIE_DOMAIN = env("COOKIE_DOMAIN", default="pycon.kr")

SESSION_COOKIE_NAME = f"{COOKIE_PREFIX}sessionid"
SESSION_COOKIE_SAMESITE = COOKIE_SAMESITE
SESSION_COOKIE_SECURE = COOKIE_SECURE
SESSION_COOKIE_HTTPONLY = COOKIE_HTTPONLY
SESSION_COOKIE_DOMAIN = None if IS_LOCAL else COOKIE_DOMAIN

CSRF_COOKIE_NAME = f"{COOKIE_PREFIX}csrftoken"
CSRF_COOKIE_SAMESITE = COOKIE_SAMESITE
CSRF_COOKIE_SECURE = COOKIE_SECURE
CSRF_COOKIE_HTTPONLY = COOKIE_HTTPONLY
CSRF_COOKIE_DOMAIN = None if IS_LOCAL else COOKIE_DOMAIN
CSRF_TRUSTED_ORIGINS = set(env.list("CSRF_TRUSTED_ORIGINS", default=["https://pycon.kr"])) | {
    "https://local.dev.pycon.kr:3000",
    "https://localhost:3000",
    "http://localhost:3000",
    "https://127.0.0.1:3000",
    "http://127.0.0.1:3000",
}

# Django Rest Framework Settings
REST_FRAMEWORK = {
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.NamespaceVersioning",
    "DEFAULT_SCHEMA_CLASS": "core.openapi.schemas.BackendAutoSchema",
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "EXCEPTION_HANDLER": "drf_standardized_errors.handler.exception_handler",
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
}

# DRF Spectacular Settings
SPECTACULAR_SETTINGS = {
    "TITLE": "PyCon KR Backend API",
    "SERVE_INCLUDE_SCHEMA": False,
}

# Sentry Settings
if SENTRY_DSN := env("SENTRY_DSN", default=""):
    SENTRY_TRACES_SAMPLE_RATE = env.float("SENTRY_TRACES_SAMPLE_RATE", default=1.0)
    SENTRY_PROFILES_SAMPLE_RATE = env.float("SENTRY_PROFILES_SAMPLE_RATE", default=0.0)
    SENTRY_IGNORED_TRACE_ROUTES = env.list("SENTRY_IGNORED_TRACE_ROUTES", default=[])

    def traces_sampler(ctx: dict[str, typing.Any]) -> float:
        """
        This function is used to determine if a transaction should be sampled.
        from https://stackoverflow.com/a/74412613
        """
        if (parent_sampled := ctx.get("parent_sampled")) is not None:
            # If this transaction has a parent, we usually want to sample it
            # if and only if its parent was sampled.
            return parent_sampled
        if "wsgi_environ" in ctx:
            # Get the URL for WSGI requests
            url = ctx["wsgi_environ"].get("PATH_INFO", "")
        elif "asgi_scope" in ctx:
            # Get the URL for ASGI requests
            url = ctx["asgi_scope"].get("path", "")
        else:
            # Other kinds of transactions don't have a URL
            url = ""
        if ctx["transaction_context"]["op"] == "http.server":
            # Conditions only relevant to operation "http.server"
            if any(url.startswith(ignored_route) for ignored_route in SENTRY_IGNORED_TRACE_ROUTES):
                return 0  # Don't trace any of these transactions
        return SENTRY_TRACES_SAMPLE_RATE

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=API_STAGE,
        release=DEPLOYMENT_RELEASE_VERSION,
        traces_sampler=traces_sampler,
        profiles_sample_rate=SENTRY_PROFILES_SAMPLE_RATE,
        send_default_pii=True,
        integrations=[
            sentry_sdk.integrations.aws_lambda.AwsLambdaIntegration(),
            sentry_sdk.integrations.django.DjangoIntegration(),
        ],
    )
