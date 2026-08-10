import re
from email.header import decode_header, make_header
from email.policy import SMTP as SMTP_EMAIL_POLICY
from smtplib import SMTPSenderRefused, SMTPServerDisconnected
from unittest.mock import MagicMock, patch

import pytest
from core.external_apis.__interface__ import SendParameters
from core.external_apis.smtp_email import EmailClient, email_client
from django.core import mail

_MAX_ENCODED_WORD_LENGTH = 75  # RFC 2047, 구분자 포함

_LONG_KOREAN_SUBJECT = (
    "[파이콘 한국] 행사 일주일 전 꼭 확인해 주세요. / [PyCon Korea] One week to go — please check before you come"
)


def _params(**overrides) -> SendParameters:
    return SendParameters(
        payload=overrides.pop("payload", {"title": "제목", "body": "<p>본문</p>"}),
        send_to=overrides.pop("send_to", "to@example.com"),
        sent_from=overrides.pop("sent_from", "from@example.com"),
        template_code=overrides.pop("template_code", ""),
    )


def _sent_subject_header() -> str:
    # SMTP 백엔드(_send)와 동일하게 policy를 명시로 넘겨 실제 발송되는 헤더를 재현한다.
    head = mail.outbox[0].message(policy=SMTP_EMAIL_POLICY).as_bytes().split(b"\r\n\r\n")[0].decode()
    return re.search(r"^Subject:(.*?)(?=^\S+:)", head + "\nX:", re.S | re.M).group(1)


@pytest.mark.parametrize(
    "subject", [_LONG_KOREAN_SUBJECT, "파이콘 한국 티켓 결제가 완료되었습니다!", "ASCII only subject"]
)
def test_send_message_subject_encoded_words_are_rfc2047_compliant(subject):
    email_client.send_message(data=_params(payload={"title": subject, "body": "<p>본문</p>"}))

    header = _sent_subject_header()
    encoded_words = [word for word in header.split() if word.startswith("=?")]
    assert all(len(word) <= _MAX_ENCODED_WORD_LENGTH for word in encoded_words)
    assert len({word.split("?")[2] for word in encoded_words}) <= 1  # base64/quoted-printable 혼용 금지
    assert str(make_header(decode_header(header.strip()))) == subject


def test_send_message_sends_html_body():
    email_client.send_message(data=_params(payload={"title": "제목", "body": "<p>본문</p>"}))

    message = mail.outbox[0]
    assert message.content_subtype == "html"
    assert message.body == "<p>본문</p>"
    assert message.to == ["to@example.com"]


def test_send_message_requires_title():
    with pytest.raises(ValueError, match="title"):
        email_client.send_message(data=_params(payload={"body": "<p>본문</p>"}))


def test_send_message_requires_sent_from():
    with pytest.raises(ValueError, match="sent_from"):
        email_client.send_message(data=_params(sent_from=""))


class TestConnectionReuse:
    # 메일마다 로그인하면 Gmail이 "454 Too many login attempts"로 차단한다.
    def test_connection_is_opened_once_and_reused(self):
        client = EmailClient()
        connection = MagicMock()
        connection.send_messages.return_value = 1

        with patch("core.external_apis.smtp_email.get_connection", return_value=connection) as factory:
            for _ in range(3):
                client.send_message(data=_params())

        assert factory.call_count == 1
        assert connection.open.call_count == 1
        assert connection.send_messages.call_count == 3
        assert connection.close.call_count == 0

    def test_disconnected_connection_is_reopened_once(self):
        client = EmailClient()
        dropped, fresh = MagicMock(), MagicMock()
        dropped.send_messages.side_effect = SMTPServerDisconnected("idle timeout")
        fresh.send_messages.return_value = 1

        with patch("core.external_apis.smtp_email.get_connection", side_effect=[dropped, fresh]):
            client.send_message(data=_params())

        assert fresh.send_messages.call_count == 1

    def test_idle_timeout_on_mail_from_is_retried(self):
        # Gmail이 유휴 커넥션에 `451 4.4.2 Timeout - closing connection`을 응답하는 경우.
        client = EmailClient()
        stale, fresh = MagicMock(), MagicMock()
        stale.send_messages.side_effect = SMTPSenderRefused(451, b"4.4.2 Timeout - closing connection.", "a@b.c")
        fresh.send_messages.return_value = 1

        with patch("core.external_apis.smtp_email.get_connection", side_effect=[stale, fresh]):
            client.send_message(data=_params())

        assert stale.close.call_count == 1
        assert fresh.send_messages.call_count == 1

    def test_permanent_sender_rejection_is_not_retried(self):
        client = EmailClient()
        connection = MagicMock()
        connection.send_messages.side_effect = SMTPSenderRefused(550, b"5.7.1 Sender denied", "a@b.c")

        with (
            patch("core.external_apis.smtp_email.get_connection", return_value=connection),
            pytest.raises(SMTPSenderRefused),
        ):
            client.send_message(data=_params())

        assert connection.send_messages.call_count == 1

    def test_repeated_disconnect_propagates(self):
        client = EmailClient()
        connection = MagicMock()
        connection.send_messages.side_effect = SMTPServerDisconnected("gone")

        with (
            patch("core.external_apis.smtp_email.get_connection", return_value=connection),
            pytest.raises(SMTPServerDisconnected),
        ):
            client.send_message(data=_params())

        assert connection.send_messages.call_count == 2
