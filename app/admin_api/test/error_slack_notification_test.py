from logging import ERROR, getLogger
from unittest.mock import Mock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework.status import HTTP_500_INTERNAL_SERVER_ERROR


@pytest.mark.django_db
@override_settings(DEBUG=False)  # 프로덕션처럼 drf-standardized-errors 가 예외를 잡아 500 응답으로 변환
@patch("file.models.PublicFile.save", side_effect=PermissionError(13, "Permission denied"))
def test_unhandled_api_500_is_logged_to_django_request_for_slack(_save, api_client):
    # drf-standardized-errors 가 예외를 응답으로 변환하면 process_exception 미들웨어가 발화하지 않으므로,
    # API 500 Slack 알림은 핸들러가 남기는 django.request(ERROR, exc_info) 로그에 의존한다(settings LOGGING 이 slack 으로 라우팅).
    api_client.raise_request_exception = False  # 프로덕션처럼 예외를 500 응답으로 변환

    handler = Mock(level=ERROR)  # django.request 에 붙는 slack 핸들러 대역
    logger = getLogger("django.request")
    logger.addHandler(handler)
    try:
        resp = api_client.post(
            path=reverse("v1:admin-public-file-upload"),
            data={"file": SimpleUploadedFile("boom.txt", b"data", content_type="text/plain")},
            format="multipart",
        )
    finally:
        logger.removeHandler(handler)

    assert resp.status_code == HTTP_500_INTERNAL_SERVER_ERROR
    handler.handle.assert_called_once()
    record = handler.handle.call_args.args[0]
    assert record.levelno == ERROR
    assert record.exc_info[0] is PermissionError
