ARG PYTHON_VERSION=3.12
FROM public.ecr.aws/lambda/python:${PYTHON_VERSION}
WORKDIR ${LAMBDA_TASK_ROOT}
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
    UV_PROJECT_ENVIRONMENT="/var/lang" \
    UV_PYTHON_DOWNLOADS=0

# Setup timezone and install gcc
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Install dependencies
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY --chown=nobody:nobody pyproject.toml uv.lock ${LAMBDA_TASK_ROOT}
RUN --mount=type=cache,target=/root/.cache/uv \
    microdnf install -y gcc \
    && microdnf clean all \
    && uv sync --no-default-groups --frozen

RUN ZAPPA_HANDLER_PATH=$(python -c 'import zappa.handler; print(zappa.handler.__file__)') \
    && echo $ZAPPA_HANDLER_PATH \
    && cp $ZAPPA_HANDLER_PATH ${LAMBDA_TASK_ROOT}

ARG GIT_HASH
ARG RELEASE_VERSION=unknown
ENV DEPLOYMENT_GIT_HASH=$GIT_HASH
ENV DEPLOYMENT_RELEASE_VERSION=$RELEASE_VERSION

# Make docker to always copy app directory so that source code can be refreshed.
ARG IMAGE_BUILD_DATETIME=unknown
ENV DEPLOYMENT_IMAGE_BUILD_DATETIME=$IMAGE_BUILD_DATETIME

# Copy main app and zappa settings
COPY --chown=nobody:nobody purchase ${LAMBDA_TASK_ROOT}/purchase
COPY --chown=nobody:nobody payment ${LAMBDA_TASK_ROOT}/payment
COPY --chown=nobody:nobody user ${LAMBDA_TASK_ROOT}/user
COPY --chown=nobody:nobody purchase_shared ${LAMBDA_TASK_ROOT}/purchase_shared
COPY --chown=nobody:nobody product ${LAMBDA_TASK_ROOT}/product
COPY --chown=nobody:nobody order ${LAMBDA_TASK_ROOT}/order
COPY --chown=nobody:nobody payment_history ${LAMBDA_TASK_ROOT}/payment_history
COPY --chown=nobody:nobody external_api ${LAMBDA_TASK_ROOT}/external_api
COPY --chown=nobody:nobody zappa_settings.py ${LAMBDA_TASK_ROOT}

# Pydantic Logfire uses OpenTelemetry, which requires the following environment variables to be set.
# See https://opentelemetry-python.readthedocs.io/en/latest/examples/django/README.html#execution-of-the-django-app
ENV DJANGO_SETTINGS_MODULE="purchase.settings"

# The reason for using nobody user is to avoid running the app as root, which can be a security risk.
USER nobody
CMD ["handler.lambda_handler"]
