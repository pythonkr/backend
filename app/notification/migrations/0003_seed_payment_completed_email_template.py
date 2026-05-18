import json
from pathlib import Path

from django.conf import settings
from django.db import migrations

# DB에 등록할 결제 완료 이메일 템플릿 코드로 교체 완료 (payment_completed.html)
# 만일 추후 변경 시 settings.NOTIFICATION.payment_completed_email_template_code 및 환경변수도 함께 수정 필요
_TEMPLATE_CODE = "payment_completed"

_EMAIL_SUBJECT = "파이콘 한국 티켓 결제가 완료되었습니다!"

_HTML_TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "payment_completed.html"


def seed_payment_completed_email_template(apps, schema_editor):
    EmailNotificationTemplate = apps.get_model("notification", "EmailNotificationTemplate")
    EmailNotificationTemplate.objects.get_or_create(
        code=_TEMPLATE_CODE,
        defaults={
            "title": "결제 완료 이메일",
            # migration 실행 시점의 환경변수(EMAIL_HOST_USER)를 발신 주소로 사용.
            # 값이 비어있으면 이메일 발송 시 오류가 발생하므로 배포 전 EMAIL_HOST_USER 설정 필요.
            "sent_from": settings.EMAIL_HOST_USER,
            "data": json.dumps(
                {
                    "title": _EMAIL_SUBJECT,
                    "body": _HTML_TEMPLATE_PATH.read_text(encoding="utf-8"),
                },
                ensure_ascii=False,
            ),
        },
    )


def reverse_seed_payment_completed_email_template(apps, schema_editor):
    EmailNotificationTemplate = apps.get_model("notification", "EmailNotificationTemplate")
    EmailNotificationTemplate.objects.filter(code=_TEMPLATE_CODE).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("notification", "0002_emailnotificationhistorysentto_failure_reason_and_more"),
    ]

    operations = [
        migrations.RunPython(
            seed_payment_completed_email_template,  # 실행할 로직
            reverse_seed_payment_completed_email_template,  # 실행할 로직에서 failure 발생 시 되돌릴 역방향 로직
        ),
    ]
