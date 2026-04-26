import logging
from unittest.mock import MagicMock, patch

import pytest
from core.external_apis.__interface__ import SendParameters
from core.external_apis.nhn_cloud_sms import nhn_cloud_sms_client


@pytest.fixture
def mock_session():
    """싱글톤 클라이언트의 httpx 세션을 mock으로 교체. NHN 표준 성공 응답을 기본값으로 반환."""
    with patch.object(nhn_cloud_sms_client, "session") as session:
        response = MagicMock()
        response.raise_for_status.return_value = response
        response.json.return_value = {
            "header": {"isSuccessful": True, "resultCode": 0, "resultMessage": "SUCCESS"},
            "body": {"data": {"requestId": "REQ-1", "statusCode": "2", "sendResultList": []}},
        }
        session.post.return_value = response
        yield session


def _params(**overrides) -> SendParameters:
    return SendParameters(
        payload=overrides.pop("payload", {"body": "Hello"}),
        send_to=overrides.pop("send_to", "01012345678"),
        sent_from=overrides.pop("sent_from", "0212345678"),
        template_code=overrides.pop("template_code", ""),
    )


# ---- send_message — 입력 검증 -----------------------------------------------


def test_send_message_raises_if_sent_from_is_none():
    with pytest.raises(ValueError, match="sent_from"):
        nhn_cloud_sms_client.send_message(data=_params(sent_from=None))


def test_send_message_raises_if_sent_from_is_empty():
    with pytest.raises(ValueError, match="sent_from"):
        nhn_cloud_sms_client.send_message(data=_params(sent_from=""))


def test_send_message_raises_if_body_missing_from_payload():
    with pytest.raises(ValueError, match="body"):
        nhn_cloud_sms_client.send_message(data=_params(payload={"title": "only title"}))


def test_send_message_raises_if_body_is_empty_string():
    with pytest.raises(ValueError, match="body"):
        nhn_cloud_sms_client.send_message(data=_params(payload={"body": ""}))


# ---- send_message — 단문 SMS / 장문 MMS 분기 ---------------------------------


def test_send_message_short_sms_hits_sender_sms_endpoint(mock_session):
    nhn_cloud_sms_client.send_message(data=_params(payload={"body": "Hello"}))

    mock_session.post.assert_called_once_with(
        "/sender/sms",
        json={
            "sendNo": "0212345678",
            "body": "Hello",
            "recipientList": [{"recipientNo": "01012345678"}],
        },
    )


def test_send_message_long_mms_hits_sender_mms_endpoint_when_title_present(mock_session):
    nhn_cloud_sms_client.send_message(data=_params(payload={"title": "공지", "body": "본문"}))

    mock_session.post.assert_called_once_with(
        "/sender/mms",
        json={
            "sendNo": "0212345678",
            "body": "본문",
            "recipientList": [{"recipientNo": "01012345678"}],
            "title": "공지",
        },
    )


def test_send_message_template_code_passed_as_template_id_when_truthy(mock_session):
    nhn_cloud_sms_client.send_message(data=_params(template_code="TEMPLATE-1"))

    sent_body = mock_session.post.call_args.kwargs["json"]
    assert sent_body["templateId"] == "TEMPLATE-1"


def test_send_message_template_id_omitted_when_template_code_empty(mock_session):
    nhn_cloud_sms_client.send_message(data=_params(template_code=""))

    sent_body = mock_session.post.call_args.kwargs["json"]
    assert "templateId" not in sent_body


def test_send_message_logs_result_code_and_message_on_success(mock_session, caplog):
    with caplog.at_level(logging.INFO, logger="core.external_apis.nhn_cloud_sms"):
        nhn_cloud_sms_client.send_message(data=_params())

    assert any("result_code=0" in r.getMessage() and "SUCCESS" in r.getMessage() for r in caplog.records)
