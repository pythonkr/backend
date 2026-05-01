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
        sent_from="from@example.com",
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


# ---- SentTo.render() (template.build_preview_sent_to 경유) ------------------


def test_render_substitutes_provided_context(email_template):
    sent_to = email_template.build_preview_sent_to({"name": "길동", "recipient": "to@example.com"})
    result = sent_to.render()
    assert result["title"] == "Hi 길동"
    assert result["body"] == "Hello 길동"
    assert result["send_to"] == "to@example.com"


def test_render_does_not_mutate_caller_context(email_template):
    context = {"name": "길동"}
    sent_to = email_template.build_preview_sent_to(context)
    sent_to.render(UnhandledVariableHandling.RANDOM)
    # `recipient`는 원본 context에 없으니 자동 채움이 발생하는데, 그게 caller dict에 새지 않아야 함
    assert context == {"name": "길동"}


def test_render_raises_by_default_on_missing_context_variables(email_template):
    # 발송 경로에서 미정의 변수가 RANDOM/REMOVE로 조용히 처리되면 사용자에게 잘못된 메시지가 나가므로,
    # 명시 없이 호출 시 ValueError로 fail-fast 해야 함.
    sent_to = email_template.build_preview_sent_to({"name": "길동"})
    with pytest.raises(ValueError, match="recipient"):
        sent_to.render()


def test_render_raise_includes_missing_vars(email_template):
    sent_to = email_template.build_preview_sent_to({"name": "길동"})
    with pytest.raises(ValueError, match=r"recipient"):
        sent_to.render()


def test_render_undefined_handling_show_as_template_var(email_template):
    sent_to = email_template.build_preview_sent_to({})
    result = sent_to.render(UnhandledVariableHandling.SHOW_AS_TEMPLATE_VAR)
    # Email은 `{{ }}` 구분자 사용
    assert result["title"] == "Hi {{ name }}"


def test_render_undefined_handling_remove(email_template):
    sent_to = email_template.build_preview_sent_to({})
    result = sent_to.render(UnhandledVariableHandling.REMOVE)
    assert result["title"] == "Hi "
    assert result["body"] == "Hello "


def test_render_undefined_handling_random_keeps_keys_filled(email_template):
    sent_to = email_template.build_preview_sent_to({})
    result = sent_to.render(UnhandledVariableHandling.RANDOM)
    assert result["title"].startswith("Hi RandomValue-")
    assert result["body"].startswith("Hello RandomValue-")


def test_render_kakao_uses_hash_brace_delimiters():
    tpl = NHNCloudKakaoAlimTalkNotificationTemplate(
        data='{"templateContent":"안녕 #{name}","buttons":[]}',
    )
    assert tpl.template_variables == {"name"}
    sent_to = tpl.build_preview_sent_to({"name": "길동"})
    assert sent_to.render()["templateContent"] == "안녕 길동"


def test_render_kakao_show_as_template_var_uses_hash_brace():
    tpl = NHNCloudKakaoAlimTalkNotificationTemplate(
        data='{"templateContent":"hi #{x}","buttons":[]}',
    )
    sent_to = tpl.build_preview_sent_to({})
    result = sent_to.render(UnhandledVariableHandling.SHOW_AS_TEMPLATE_VAR)
    # Kakao는 `#{ }` 구분자
    assert result["templateContent"] == "hi #{ x }"


# ---- SentTo.render_as_html() ------------------------------------------------


def test_render_as_html_email_preview_returns_html(email_template):
    sent_to = email_template.build_preview_sent_to({"name": "길동", "recipient": "to@example.com"})
    html = sent_to.render_as_html()
    assert html.strip().startswith("<html")
    assert "길동" in html


def test_render_as_html_kakao_preview_renders_buttons():
    tpl = NHNCloudKakaoAlimTalkNotificationTemplate(
        data='{"templateContent":"hi","buttons":[{"name":"가기","linkMo":"https://x"}]}',
    )
    sent_to = tpl.build_preview_sent_to({})
    html = sent_to.render_as_html()
    assert 'href="https://x"' in html
    assert "가기" in html


# ---- JSON-unsafe context (per-string substitution 검증) -----------------------


def test_render_preserves_double_quote_in_context(email_template):
    # context에 `"`가 들어가도 JSON 파싱이 깨지지 않고 raw 그대로 전달됨.
    sent_to = email_template.build_preview_sent_to({"name": '길동"injected', "recipient": "to@x"})
    result = sent_to.render()
    assert result["body"] == 'Hello 길동"injected'


def test_render_preserves_backslash_and_newline_in_context():
    tpl = EmailNotificationTemplate(
        sent_from="from@example.com",
        data='{"title":"x","from_":"f","send_to":"r","body":"{{ msg }}"}',
    )
    sent_to = tpl.build_preview_sent_to({"msg": "line1\nline2\\path"})
    result = sent_to.render()
    assert result["body"] == "line1\nline2\\path"


def test_render_kakao_button_array_substitutes_nested_strings():
    # nested dict/list 안의 string에도 변수 치환이 적용됨.
    tpl = NHNCloudKakaoAlimTalkNotificationTemplate(
        data='{"templateContent":"안녕 #{name}","buttons":[{"name":"#{label}","linkMo":"https://x"}]}',
    )
    sent_to = tpl.build_preview_sent_to({"name": "길동", "label": "확인"})
    result = sent_to.render()
    assert result["templateContent"] == "안녕 길동"
    assert result["buttons"][0]["name"] == "확인"
    assert result["buttons"][0]["linkMo"] == "https://x"


def test_template_variables_collects_from_nested_strings():
    tpl = NHNCloudKakaoAlimTalkNotificationTemplate(
        data='{"templateContent":"#{a}","buttons":[{"name":"#{b}","linkMo":"#{c}"}]}',
    )
    assert tpl.template_variables == {"a", "b", "c"}
