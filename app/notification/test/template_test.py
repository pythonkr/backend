import pytest
from notification.models import (
    EmailNotificationTemplate,
    NHNCloudKakaoAlimTalkNotificationTemplate,
)
from notification.models.base import UnhandledVariableHandling


# 인메모리 인스턴스 — render/template_variables는 DB 영속화가 필요하지 않음.
@pytest.fixture
def email_template():
    return EmailNotificationTemplate(
        code="welcome",
        title="Welcome",
        from_address="from@example.com",
        data='{"title":"Hi {{ name }}","from_":"f","send_to":"{{ recipient }}","body":"Hello {{ name }}"}',
    )


# ---- 템플릿 변수 추출 ---------------------------------------------------------


def test_template_variables_extracts_root_variables_from_data(email_template):
    assert email_template.template_variables == {"name", "recipient"}


def test_template_variables_excludes_literal_constant_expressions():
    # `{{ "hello" }}` 같은 상수 표현은 변수가 아니므로 잡히면 안 됨
    constant_only = EmailNotificationTemplate(data='hello {{ "literal" }} world')
    assert constant_only.template_variables == set()
    tpl = EmailNotificationTemplate(data='{"title":"x","from_":"f","send_to":"r","body":"{{ name }}"}')
    assert tpl.template_variables == {"name"}


def test_template_variables_dotted_path_keeps_root_only():
    tpl = EmailNotificationTemplate(data='{"title":"{{ user.name }}","from_":"f","send_to":"r","body":"x"}')
    assert tpl.template_variables == {"user"}


# ---- render() ---------------------------------------------------------------


def test_render_substitutes_provided_context(email_template):
    result = email_template.render({"name": "길동", "recipient": "to@example.com"})
    assert result["title"] == "Hi 길동"
    assert result["body"] == "Hello 길동"
    assert result["send_to"] == "to@example.com"


def test_render_does_not_mutate_caller_context(email_template):
    context = {"name": "길동"}
    email_template.render(context, UnhandledVariableHandling.RANDOM)
    # `recipient`는 원본 context에 없으니 자동 채움이 발생하는데, 그게 caller dict에 새지 않아야 함
    assert context == {"name": "길동"}


def test_render_raises_by_default_on_missing_context_variables(email_template):
    # 발송 경로에서 미정의 변수가 RANDOM/REMOVE로 조용히 처리되면 사용자에게 잘못된 메시지가 나가므로,
    # 명시 없이 호출 시 ValueError로 fail-fast 해야 함.
    with pytest.raises(ValueError, match="recipient"):
        email_template.render({"name": "길동"})


def test_render_raise_includes_template_code_and_missing_vars(email_template):
    with pytest.raises(ValueError, match=r"welcome.*recipient"):
        email_template.render({"name": "길동"})


def test_render_undefined_handling_show_as_template_var(email_template):
    result = email_template.render({}, UnhandledVariableHandling.SHOW_AS_TEMPLATE_VAR)
    # Email은 `{{ }}` 구분자 사용
    assert result["title"] == "Hi {{ name }}"


def test_render_undefined_handling_remove(email_template):
    result = email_template.render({}, UnhandledVariableHandling.REMOVE)
    assert result["title"] == "Hi "
    assert result["body"] == "Hello "


def test_render_undefined_handling_random_keeps_keys_filled(email_template):
    result = email_template.render({}, UnhandledVariableHandling.RANDOM)
    assert result["title"].startswith("Hi RandomValue-")
    assert result["body"].startswith("Hello RandomValue-")


def test_render_kakao_uses_hash_brace_delimiters():
    tpl = NHNCloudKakaoAlimTalkNotificationTemplate(
        data='{"templateContent":"안녕 #{name}","buttons":[]}',
    )
    assert tpl.template_variables == {"name"}
    assert tpl.render({"name": "길동"})["templateContent"] == "안녕 길동"


def test_render_kakao_show_as_template_var_uses_hash_brace():
    tpl = NHNCloudKakaoAlimTalkNotificationTemplate(
        data='{"templateContent":"hi #{x}","buttons":[]}',
    )
    result = tpl.render({}, UnhandledVariableHandling.SHOW_AS_TEMPLATE_VAR)
    # Kakao는 `#{ }` 구분자
    assert result["templateContent"] == "hi #{ x }"


# ---- render_as_html() -------------------------------------------------------


def test_render_as_html_email_preview_returns_html(email_template):
    html = email_template.render_as_html({"name": "길동", "recipient": "to@example.com"})
    assert html.strip().startswith("<html")
    assert "길동" in html


def test_render_as_html_kakao_preview_renders_buttons():
    tpl = NHNCloudKakaoAlimTalkNotificationTemplate(
        data='{"templateContent":"hi","buttons":[{"name":"가기","linkMo":"https://x"}]}',
    )
    html = tpl.render_as_html({})
    assert 'href="https://x"' in html
    assert "가기" in html
