from unittest.mock import MagicMock, patch

import pytest
from core.external_apis.__interface__ import NotificationSendError, SendParameters
from core.external_apis.nhn_cloud.kakao_alimtalk import nhn_cloud_kakao_alimtalk_client


@pytest.fixture
def mock_session():
    """싱글톤 클라이언트의 httpx 세션을 mock으로 교체. NHN 표준 성공 응답을 기본값으로 반환."""
    with patch.object(nhn_cloud_kakao_alimtalk_client, "session") as session:
        response = MagicMock()
        response.raise_for_status.return_value = response
        response.json.return_value = {
            "header": {"isSuccessful": True, "resultCode": 0, "resultMessage": "success"},
            "message": {"sendResults": [{"recipientNo": "01012345678", "resultCode": 0, "resultMessage": "SUCCESS"}]},
        }
        session.post.return_value = response
        yield session


def _params(**overrides) -> SendParameters:
    return SendParameters(
        payload=overrides.pop("payload", {"customer_name": "홍길동"}),
        send_to=overrides.pop("send_to", "01012345678"),
        sent_from=overrides.pop("sent_from", "SENDER-KEY"),
        template_code=overrides.pop("template_code", "tpl_1"),
    )


def test_send_message_raises_if_sent_from_is_empty():
    with pytest.raises(ValueError, match="sent_from"):
        nhn_cloud_kakao_alimtalk_client.send_message(data=_params(sent_from=""))


def test_send_message_posts_expected_body(mock_session):
    nhn_cloud_kakao_alimtalk_client.send_message(data=_params())

    mock_session.post.assert_called_once_with(
        "/messages",
        json={
            "senderKey": "SENDER-KEY",
            "templateCode": "tpl_1",
            "recipientList": [{"recipientNo": "01012345678", "templateParameter": {"customer_name": "홍길동"}}],
        },
    )


def test_send_message_raises_when_recipient_failed_with_http_200(mock_session):
    # NHN은 수신자가 거부돼도 HTTP 200 + header.isSuccessful=false 로 응답한다.
    mock_session.post.return_value.json.return_value = {
        "header": {"isSuccessful": False, "resultCode": -1031, "resultMessage": "All of receivers are failed to send."},
        "message": {
            "sendResults": [
                {"recipientNo": "01012345678", "resultCode": -1028, "resultMessage": "Blacklist can't use ..."}
            ]
        },
    }
    with pytest.raises(NotificationSendError, match="-1028"):
        nhn_cloud_kakao_alimtalk_client.send_message(data=_params())


def test_send_message_raises_when_header_unsuccessful_without_send_results(mock_session):
    mock_session.post.return_value.json.return_value = {
        "header": {"isSuccessful": False, "resultCode": -1, "resultMessage": "auth failed"},
    }
    with pytest.raises(NotificationSendError, match="Alimtalk"):
        nhn_cloud_kakao_alimtalk_client.send_message(data=_params())


def test_send_message_raises_cleanly_when_message_is_null(mock_session):
    # NHN이 message를 null로 주더라도 AttributeError가 아니라 명확한 예외여야 한다.
    mock_session.post.return_value.json.return_value = {
        "header": {"isSuccessful": False, "resultCode": -1, "resultMessage": "fail"},
        "message": None,
    }
    with pytest.raises(NotificationSendError, match="Alimtalk"):
        nhn_cloud_kakao_alimtalk_client.send_message(data=_params())
