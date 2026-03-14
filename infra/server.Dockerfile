ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim
WORKDIR /app
SHELL [ "/bin/bash", "-euxvc"]

ENV PATH="${PATH}:/root/.local/bin:" \
    TZ=Asia/Seoul \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONIOENCODING=UTF-8 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_CONCURRENT_DOWNLOADS=32 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT="/usr/local" \
    UV_PYTHON_DOWNLOADS=0

# Setup timezone and install system dependencies
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Install dependencies
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY --chown=nobody:nobody pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/* \
    && uv sync --no-default-groups --frozen

ARG GIT_HASH
ARG RELEASE_VERSION=unknown
ENV DEPLOYMENT_GIT_HASH=$GIT_HASH
ENV DEPLOYMENT_RELEASE_VERSION=$RELEASE_VERSION

# Make docker to always copy app directory so that source code can be refreshed.
ARG IMAGE_BUILD_DATETIME=unknown
ENV DEPLOYMENT_IMAGE_BUILD_DATETIME=$IMAGE_BUILD_DATETIME

# Copy main app
COPY --chown=nobody:nobody app/ ./

ENV DJANGO_SETTINGS_MODULE="core.settings"

EXPOSE 8000

# The reason for using nobody user is to avoid running the app as root, which can be a security risk.
USER nobody
CMD ["gunicorn", "core.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "30"]
