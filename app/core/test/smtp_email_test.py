import re
from email.header import decode_header, make_header

import pytest
from core.external_apis.__interface__ import SendParameters
from core.external_apis.smtp_email import email_client
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
    head = mail.outbox[0].message().as_bytes().split(b"\r\n\r\n")[0].decode()
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
