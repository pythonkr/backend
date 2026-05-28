import os
import pathlib
import types
import typing

import corsheaders.defaults
import environ
import sentry_sdk
import sentry_sdk.integrations.django

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
SLACK = types.SimpleNamespace(
    token=env("SLACK_LOG_TOKEN", default=""),
    channel=env("SLACK_LOG_CHANNEL", default=""),
    modification_audit_notification_channel=env("SLACK_MODIFICATION_AUDIT_NOTIFICATION_CHANNEL", default=""),
)

LOG_LEVEL = env("LOG_LEVEL")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "basic": {"format": "%(asctime)s:%(module)s:%(levelname)s:%(message)s", "datefmt": "%Y-%m-%d %H:%M:%S"},
        "slack": {"()": "core.logger.formatter.slack.SlackJsonFormatter"},
    },
    "handlers": {
        "console": {
            "level": LOG_LEVEL,
            "class": "logging.StreamHandler",
            "formatter": "basic",
        },
        "slack": {
            "level": LOG_LEVEL,
            "class": "core.logger.handler.slack.SlackHandler",
            "formatter": "slack",
        },
    },
    "loggers": {
        "django.db.backends": ({"level": LOG_LEVEL, "handlers": ["console"]} if IS_LOCAL else {}),
        "request_logger": {"level": LOG_LEVEL, "handlers": ["console"], "propagate": True},
        "slack_logger": ({"level": LOG_LEVEL, "handlers": ["slack"]} if SLACK.token and SLACK.channel else {}),
    },
}

API_STAGE = env("API_STAGE", default="prod")

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
    for port in ("", ":3000", ":5173", ":5174")
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
    "django.contrib.postgres",
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
    # For Shell Plus
    "django_extensions",
    # Django-Allauth
    "allauth",
    "allauth.account",
    "allauth.headless",
    "allauth.socialaccount",
    "allauth.usersessions",
    "allauth.socialaccount.providers.github",
    "allauth.socialaccount.providers.google",
    "allauth.socialaccount.providers.kakao",
    "allauth.socialaccount.providers.naver",
    # django-app
    "user",
    "file",
    "cms",
    "event",
    "event.presentation",
    "event.sponsor",
    "shop.order",
    "shop.product",
    "shop.payment_history",
    "notification",
    "admin_api",
    "internal_api",
    "participant_portal_api",
    "external_api",
    "external_api.google_oauth2",
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
    # Django-Allauth
    "allauth.account.middleware.AccountMiddleware",
    "core.middleware.append_session_token_for_local_callback.AppendSessionTokenForLocalCallbackMiddleware",
    # session-check endpoint 응답에 항상 Set-Cookie sessionid 부착 (rolling expiry + localhost cookie 동기화).
    # 반드시 SessionMiddleware보다 뒤에 둘 것 — response phase가 역순이라 이 미들웨어가 먼저 실행되어
    # session.modified=True 플래그를 세팅한 뒤 SessionMiddleware의 response 처리가 그걸 보고 cookie를 쓴다.
    "core.middleware.force_session_save_on_session_check.ForceSessionSaveOnSessionCheckMiddleware",
    # Thread Local Middleware
    "core.middleware.thread_middleware.ThreadLocalMiddleware",
    # Request Response Logger
    "core.middleware.request_response_logger.RequestResponseLogger",
]

ROOT_URLCONF = "core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": ["core/templates", "notification/templates"],
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

if env.str("LEGACY_DATABASE_NAME", default=""):
    DATABASES["legacy"] = {**DATABASES["default"], "NAME": env.str("LEGACY_DATABASE_NAME")}


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

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

# Django-Allauth
AUTHENTICATION_BACKENDS = [
    # Django admin / 기본 로그인
    "django.contrib.auth.backends.ModelBackend",
    # allauth (email login 등)
    "allauth.account.auth_backends.AuthenticationBackend",
    # 외부 등록 데스크 등 API key 인증
    "core.authn.api_key.APIKeyAuthentication",
]

ACCOUNT_DEFAULT_HTTP_PROTOCOL = "https"
ACCOUNT_LOGIN_METHODS = {"username", "email"}
ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_ADAPTER = "core.authn.allauth_adapter.NoNewUsersAccountAdapter"

SOCIALACCOUNT_ONLY = False
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
SOCIALACCOUNT_EMAIL_REQUIRED = True
SOCIALACCOUNT_ADAPTER = "core.authn.allauth_adapter.SocialAccountLoggingAdapter"
SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
    },
}

HEADLESS_ONLY = True
HEADLESS_ADAPTER = "core.authn.allauth_adapter.PyConKRHeadlessAdapter"
HEADLESS_FRONTEND_URLS: dict[str, str] = {}


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

DATA_UPLOAD_MAX_MEMORY_SIZE = 30 * 1024 * 1024  # 30 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 30 * 1024 * 1024  # 30 MB

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
        "bucket_name": PUBLIC_STORAGE_BUCKET_NAME,
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
COOKIE_DOMAIN = env("COOKIE_DOMAIN", default="pycon.kr") if not IS_LOCAL else None
COOKIE_TRUSTED_ORIGIN_SET = {
    f"{protocol}://{domain}:{port}"
    for protocol in ("http", "https")
    for domain in ("localhost", "127.0.0.1", "local.dev.pycon.kr")
    for port in (3000, 5173, 5174)
}

SESSION_COOKIE_NAME = f"{COOKIE_PREFIX}sessionid"
SESSION_COOKIE_SAMESITE = COOKIE_SAMESITE
SESSION_COOKIE_SECURE = COOKIE_SECURE
SESSION_COOKIE_HTTPONLY = env.bool("SESSION_COOKIE_HTTPONLY", default=COOKIE_HTTPONLY)
SESSION_COOKIE_DOMAIN = COOKIE_DOMAIN

CSRF_COOKIE_NAME = f"{COOKIE_PREFIX}csrftoken"
CSRF_COOKIE_SAMESITE = COOKIE_SAMESITE
CSRF_COOKIE_SECURE = COOKIE_SECURE
CSRF_COOKIE_HTTPONLY = False  # CSRF_COOKIE_HTTPONLY must be False to allow JavaScript to read the CSRF token
CSRF_COOKIE_DOMAIN = COOKIE_DOMAIN
CSRF_TRUSTED_ORIGINS = (
    set(env.list("CSRF_TRUSTED_ORIGINS", default=["https://rest-api.pycon.kr"])) | COOKIE_TRUSTED_ORIGIN_SET
)

# Frontend domain settings
BACKEND_DOMAIN = env("BACKEND_DOMAIN", default="https://rest-api.pycon.kr")
FRONTEND_DOMAIN = types.SimpleNamespace(
    main=env.list("FRONTEND_MAIN_URLS", default=["https://pycon.kr"]),
    admin=env("FRONTEND_ADMIN_URL", default="https://admin.pycon.kr"),
    participant=env("FRONTEND_PARTICIPANT_URL", default="https://participant.pycon.kr"),
)

# Django Rest Framework Settings
REST_FRAMEWORK = {
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.NamespaceVersioning",
    "DEFAULT_SCHEMA_CLASS": "core.openapi.schemas.BackendAutoSchema",
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "EXCEPTION_HANDLER": "drf_standardized_errors.handler.exception_handler",
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "URL_FORMAT_OVERRIDE": None,
}

# DRF Spectacular Settings
SPECTACULAR_SETTINGS = {
    "TITLE": "PyCon KR Backend API",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SWAGGER_UI_SETTINGS": {
        "docExpansion": "none",  # Collapse all endpoints by default
    },
}

GOOGLE_CLOUD = types.SimpleNamespace(
    CLIENT_ID=env("GOOGLE_OAUTH_CLIENT_ID", default=""),
    CLIENT_SECRET=env("GOOGLE_OAUTH_CLIENT_SECRET", default=""),
    SCOPES=env.list("GOOGLE_OAUTH_SCOPES", default=[]),
)

# Email (Gmail OAuth2) Settings — host/port/SSL은 Gmail 전용 고정값.
# 로컬 개발은 envfile에서 EMAIL_BACKEND를 console 백엔드로 오버라이드.
EMAIL_BACKEND = env("EMAIL_BACKEND", default="core.email_backends.GmailOAuth2Backend")
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 465
EMAIL_USE_SSL = True
EMAIL_USE_TLS = False
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_TIMEOUT = env.float("EMAIL_TIMEOUT", default=30.0)

# NHN Cloud Settings
# https://docs.nhncloud.com/ko/Notification/KakaoTalk%20Bizmessage/ko/alimtalk-api-guide/
# https://docs.nhncloud.com/ko/Notification/SMS/ko/api-guide/
NHN_CLOUD = types.SimpleNamespace(
    app_key=env("NHN_CLOUD_APP_KEY", default=""),
    secret_key=env("NHN_CLOUD_SECRET_KEY", default=""),
    kakao_alimtalk=types.SimpleNamespace(
        base_url=env(
            "NHN_CLOUD_KAKAO_ALIMTALK_BASE_URL", default="https://kakaotalk-bizmessage.api.nhncloudservice.com"
        ),
        timeout=env.float("NHN_CLOUD_KAKAO_ALIMTALK_TIMEOUT", default=30.0),
    ),
    sms=types.SimpleNamespace(
        base_url=env("NHN_CLOUD_SMS_BASE_URL", default="https://sms.api.nhncloudservice.com"),
        timeout=env.float("NHN_CLOUD_SMS_TIMEOUT", default=30.0),
    ),
)

# Celery Settings
CELERY_BROKER_URL = env("CELERY_BROKER_URL")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND")
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_SOFT_TIME_LIMIT = 60
CELERY_TASK_TIME_LIMIT = 90

# PortOne Settings
PORTONE = types.SimpleNamespace(
    api_url=env("PORTONE_API_URL", default="https://api.iamport.kr"),
    ip_list=env.list(
        "PORTONE_IP_LIST",
        default=[
            "52.78.100.19",
            "52.78.48.223",
            "52.78.5.241",  # (Webhook Test Only)
        ],
    ),
    imp_key=env("PORTONE_IMP_KEY", default="imp_key"),
    imp_secret=env("PORTONE_IMP_SECRET", default="imp_secret"),
)

# NHN KCP Settings
NHN_KCP = types.SimpleNamespace(
    pg_api_cert=env.str("NHN_KCP_PG_API_CERT", default=""),
    pg_api_private_key=env.str("NHN_KCP_PG_API_PRIVATE_KEY", default=""),
    pg_api_password=env.str("NHN_KCP_PG_API_PASSWORD", default=""),
)

# Shop Settings
SHOP = types.SimpleNamespace(
    order_scancode_salt=env("ORDER_SCANCODE_SALT", default="local_order_scancode_salt"),
    refund_authorizer_secret_key=env("REFUND_AUTHORIZER_SECRET_KEY", default="local_refund_authorizer_secret_key"),
)

# Notification Settings
NOTIFICATION = types.SimpleNamespace(
    #  NHN Cloud → DB 동기화 후 해당 code로 템플릿을 조회합니다.
    payment_completed_alimtalk_template_code=env.str(
        "PAYMENT_COMPLETED_ALIMTALK_TEMPLATE_CODE", default="pycon_2026_paid"
    ),
    # DB에 등록된 결제 완료 이메일 템플릿 코드로 교체 완료
    payment_completed_email_template_code=env.str("PAYMENT_COMPLETED_EMAIL_TEMPLATE_CODE", default="payment_completed"),
)

# External API Key Settings (등록 데스크 등)
EXT_API_KEYS = {
    "registration_desk": env("API_KEY_REGISTRATION_DESK", default=None),
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
            sentry_sdk.integrations.django.DjangoIntegration(),
        ],
    )
