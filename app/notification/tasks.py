from traceback import format_exc

from celery import shared_task
from django.apps import apps
from notification.models.base import NotificationStatus, slack_logger


@shared_task(ignore_result=True)
def send_notification_to_recipient(model_label: str, sent_to_id: str) -> None:
    sent_to_class = apps.get_model(model_label)
    sent_to = sent_to_class.objects.select_related("history").get(pk=sent_to_id)
    if sent_to.status not in (NotificationStatus.CREATED, NotificationStatus.FAILED):
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
