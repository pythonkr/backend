import contextlib
import json
import types

from django.http.request import HttpRequest, RawPostDataException
from django.http.response import HttpResponseBase
from rest_framework.request import Request

PLACEHOLDER_AWS_REQUEST_ID = "00000000-0000-0000-0000-000000000000"
PLACEHOLDER_AWS_LAMBDA_CONTEXT = types.SimpleNamespace(AWS_REQUEST_ID=PLACEHOLDER_AWS_REQUEST_ID)


def default_json_dumps(obj: object, **kwargs) -> str:
    return json.dumps(
        obj=obj,
        skipkeys=True,
        ensure_ascii=False,
        default=lambda o: o.__dict__ if hasattr(o, "__dict__") else str(o),
        **kwargs,
    )


def get_request_log_data(request: HttpRequest | Request) -> dict[str, str | dict]:
    # Request에 headers와 body의 크기를 합쳐서 100kib가 넘는 경우, 로깅을 하지 않도록 수정해야 합니다.
    try:
        body = request.data if isinstance(request, Request) else request.body.decode("utf-8", "ignore")
    except RawPostDataException:
        body = "Request body is not readable."

    request_data = {
        "method": request.method,
        "path": request.path,
        "user": request.user.username if request.user.is_authenticated else None,
        "query_params": request.GET,
        "headers": dict(request.headers),
        "body": body,
    }
    with contextlib.suppress(json.JSONDecodeError):
        if json.dumps(request_data).encode("utf-8").__sizeof__() > 102400:
            request_data["query_params"] = "Query params are filtered out due to large size."
            request_data["headers"] = "Request headers are filtered out due to large size."
            request_data["body"] = "Request body is filtered out due to large size."

    return request_data


def get_response_log_data(response: HttpResponseBase) -> dict[str, str | dict]:
    response_body = getattr(response, "content", getattr(response, "streaming_content", "Couldn't get response body"))
    with contextlib.suppress(json.JSONDecodeError, TypeError):
        response_body = response_body and json.loads(response_body)

    with contextlib.suppress(json.JSONDecodeError, TypeError):
        if json.dumps(response_body).encode("utf-8").__sizeof__() > 102400:
            response_body = "Response body is filtered out due to large size."

    return {
        "status_code": response.status_code,
        "headers": dict(response.headers),
        "body": response_body,
    }


def get_aws_request_id_from_request(request: HttpRequest) -> str:
    lambda_context = request.META.get("lambda.context", PLACEHOLDER_AWS_LAMBDA_CONTEXT)
    if aws_request_id := getattr(lambda_context, "AWS_REQUEST_ID", None):
        return aws_request_id
    return getattr(lambda_context, "aws_request_id", PLACEHOLDER_AWS_REQUEST_ID)
