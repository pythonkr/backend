import pytest
from core.const.regex import HOSTNAME_REGEX


@pytest.mark.parametrize(
    "domain",
    [
        "pycon.kr",
        "2025.pycon.kr",
        "a",
        "sub.domain.example.com",
    ],
)
def test_hostname_re_accepts_valid(domain):
    assert HOSTNAME_REGEX.match(domain)


@pytest.mark.parametrize(
    "domain",
    [
        "https://pycon.kr",  # 스킴
        "pycon.kr:8080",  # 포트
        "pycon.kr/path",  # 경로
        "pycon.kr?q=1",  # 쿼리
        "pycon..kr",  # 연속 점
        "-pycon.kr",  # 하이픈으로 시작
        "pycon.kr-",  # 하이픈으로 끝
        "PYCON.KR",  # 대문자 (정규화 안 된 입력은 거부)
        " pycon.kr",  # 공백 (정규화 안 된 입력은 거부)
    ],
)
def test_hostname_re_rejects_invalid(domain):
    assert not HOSTNAME_REGEX.match(domain)
