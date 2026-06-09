from core.logger.util.django_helper import get_response_log_data
from django.http import HttpResponse


def test_get_response_log_data_parses_json_body():
    response = HttpResponse(content=b'{"a": 1}', content_type="application/json")
    assert get_response_log_data(response)["body"] == {"a": 1}


def test_get_response_log_data_keeps_text_body_as_string():
    response = HttpResponse(content=b"<html>hi</html>", content_type="text/html")
    assert get_response_log_data(response)["body"] == "<html>hi</html>"


def test_get_response_log_data_does_not_crash_on_binary_body():
    # 0xda 는 utf-8 로 디코딩할 수 없어 json.loads 가 UnicodeDecodeError 를 던지던 케이스
    pdf_bytes = b"%PDF-1.4\xda\xde\xad\xbe\xef"
    response = HttpResponse(content=pdf_bytes, content_type="application/pdf")

    body = get_response_log_data(response)["body"]

    assert isinstance(body, str)
    assert body == f"Binary response body ({len(pdf_bytes)} bytes) is not logged."
