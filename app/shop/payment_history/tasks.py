import logging

from celery import shared_task

slack_logger = logging.getLogger("slack_logger")
logger = logging.getLogger(__name__)


@shared_task(ignore_result=True)
def send_payment_completed_notifications(order_id: str) -> None:
    """결제 완료 시 알림톡 + 이메일 자동 발송 (비동기 Celery task).

    - customer_info가 없는 주문은 발송을 건너뛰고 slack_logger로 누락 사실을 기록합니다.
    - 알림톡과 이메일은 독립적으로 시도되며, 한 채널 실패가 다른 채널 발송을 막지 않습니다.
    - 실제 외부 API 호출은 send_notification_to_recipient task에서 채널별로 처리됩니다.
    """
    from django.conf import settings
    from shop.order.models import Order

    order = Order.objects.filter_active().select_related("customer_info").filter(id=order_id).first()

    if order is None:
        slack_logger.error("결제 완료 알림 발송 실패: 주문을 찾을 수 없습니다. order_id=%s", order_id)
        return

    customer_info = getattr(order, "customer_info", None)
    if customer_info is None:
        slack_logger.error(
            "결제 완료 알림 발송 누락: customer_info가 없는 주문입니다. order_id=%s",
            order_id,
        )
        return

    # TODO: 알림톡/이메일 템플릿 변수 확정 후 context 업데이트 필요.
    #       템플릿에서 사용하는 #{변수명} / {{ 변수명 }} 목록에 맞게 값을 추가하세요.
    context = {
        "phone": customer_info.phone,
        "email": customer_info.email,
    }

    _send_alimtalk(order_id, customer_info.phone, context, settings)
    _send_email(order_id, customer_info.email, context, settings)


def _send_alimtalk(order_id: str, recipient_phone: str, context: dict, settings) -> None:
    from notification.models import (
        NHNCloudKakaoAlimTalkNotificationHistory,
        NHNCloudKakaoAlimTalkNotificationTemplate,
    )

    try:
        template_code = settings.NOTIFICATION.payment_completed_alimtalk_template_code
        template = NHNCloudKakaoAlimTalkNotificationTemplate.objects.filter_active().filter(code=template_code).first()
        if template is None:
            slack_logger.error(
                "결제 완료 알림톡 발송 실패: 템플릿을 찾을 수 없습니다. template_code=%s order_id=%s",
                template_code,
                order_id,
            )
            return

        history = NHNCloudKakaoAlimTalkNotificationHistory.objects.create_for_recipients(
            template=template,
            recipients=[{"recipient": recipient_phone, "context": context}],
        )
        history.send()
    except Exception:
        slack_logger.exception(
            "결제 완료 알림톡 발송 중 예외 발생. order_id=%s",
            order_id,
        )


def _send_email(order_id: str, recipient_email: str, context: dict, settings) -> None:
    from notification.models import EmailNotificationHistory, EmailNotificationTemplate

    try:
        template_code = settings.NOTIFICATION.payment_completed_email_template_code
        template = EmailNotificationTemplate.objects.filter_active().filter(code=template_code).first()
        if template is None:
            # 이메일 템플릿은 아직 미생성 상태일 수 있으므로 warning 수준으로 기록.
            logger.warning(
                "결제 완료 이메일 발송 건너뜀: 템플릿을 찾을 수 없습니다. template_code=%s order_id=%s",
                template_code,
                order_id,
            )
            return

        history = EmailNotificationHistory.objects.create_for_recipients(
            template=template,
            recipients=[{"recipient": recipient_email, "context": context}],
        )
        history.send()
    except Exception:
        slack_logger.exception(
            "결제 완료 이메일 발송 중 예외 발생. order_id=%s",
            order_id,
        )
