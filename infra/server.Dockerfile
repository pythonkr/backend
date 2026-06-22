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
    UV_PYTHON_DOWNLOADS=0 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Setup timezone and install system dependencies
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Install dependencies
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY --chown=nobody:nobody pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    apt-get update \
    && apt-get install -y --no-install-recommends gcc curl libpq-dev libpango-1.0-0 libpangoft2-1.0-0 fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/* \
    && uv sync --no-default-groups --group mcp --frozen

# Bundle Chromium for the MCP `mdx_preview` tool. The browser download is cached
# across builds via a BuildKit cache mount, then copied into the image (cache mounts
# aren't persisted into layers). Kept before `COPY app/` so app-code changes never
# re-trigger it. PLAYWRIGHT_BROWSERS_PATH (set above) is where the runtime looks.
RUN --mount=type=cache,target=/opt/pw-cache \
    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-cache playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p "$PLAYWRIGHT_BROWSERS_PATH" \
    && cp -a /opt/pw-cache/. "$PLAYWRIGHT_BROWSERS_PATH"/ \
    && chmod -R a+rX "$PLAYWRIGHT_BROWSERS_PATH"

# The nobody user has no writable fontconfig cache dir, which triggers "Fontconfig error: No writable cache directories" on every WeasyPrint render.
# Give it a writable cache path.
ENV XDG_CACHE_HOME=/tmp

ARG GIT_HASH
ARG RELEASE_VERSION=unknown
ENV DEPLOYMENT_GIT_HASH=$GIT_HASH
ENV DEPLOYMENT_RELEASE_VERSION=$RELEASE_VERSION

# Make docker to always copy app directory so that source code can be refreshed.
ARG IMAGE_BUILD_DATETIME=unknown
ENV DEPLOYMENT_IMAGE_BUILD_DATETIME=$IMAGE_BUILD_DATETIME

# Copy main app
COPY --chown=nobody:nobody app/ ./

# Copy the standalone MCP server package (Django-free; same image runs it via
# `python -m mcp_app`). WORKDIR is /app, so the package resolves at /app/mcp_app.
COPY --chown=nobody:nobody mcp_app/ ./mcp_app/

ENV DJANGO_SETTINGS_MODULE="core.settings"

# 8000=Django(gunicorn), 9000=MCP(python -m mcp_app)
EXPOSE 8000 9000

# The reason for using nobody user is to avoid running the app as root, which can be a security risk.
USER nobody
CMD ["gunicorn", "core.wsgi:application", "-c", "core/gunicorn_conf.py"]
