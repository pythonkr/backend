from smtplib import SMTPAuthenticationError, SMTPConnectError
from traceback import format_exc

from celery import shared_task
from django.apps import apps
from notification.models.base import NotificationStatus, slack_logger


# 연결/인증 단계 실패만 재시도한다 — 메시지 전송이 시작된 뒤의 예외는 중복 발송 위험이 있다.
# Gmail은 짧은 시간에 로그인이 몰리면 XOAUTH2를 일시 거부하므로 백오프가 필요하다.
# rate_limit은 worker 단위이고 채널 공통 — 분당 90건대에서 Gmail이 차단했던 이력을 기준으로 여유를 뒀다.
# 운영 중 조정은 배포 없이 `app.control.rate_limit(task_name, "30/m")`로 가능하다.
@shared_task(
    ignore_result=True,
    rate_limit="60/m",
    autoretry_for=(SMTPAuthenticationError, SMTPConnectError),
    retry_backoff=30,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
)
def send_notification_to_recipient(model_label: str, sent_to_id: str, force: bool = False) -> None:
    sent_to_class = apps.get_model(model_label)
    sent_to = sent_to_class.objects.select_related("history").get(pk=sent_to_id)
    if not force and sent_to.status not in (NotificationStatus.CREATED, NotificationStatus.FAILED):
        return

    try:
        sent_to.send()
    except Exception:
        sent_to.refresh_from_db(fields=["status"])
        if sent_to.status != NotificationStatus.FAILED:
            sent_to_class.objects.filter(pk=sent_to_id).update(
                status=NotificationStatus.FAILED,
                failure_reason=format_exc(),
            )
            slack_logger.exception(
                "Batch send unexpected error: history_id=%s recipient=%s",
                sent_to.history_id,
                sent_to.recipient,
            )
        raise
