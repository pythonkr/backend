from re import compile as re_compile
from typing import Any, ClassVar, Self

from core.external_apis.nhn_cloud_kakao_alimtalk import NHNCloudKakaoAlimTalkClient, nhn_cloud_kakao_alimtalk_client
from core.logger.util.django_helper import default_json_dumps
from core.models import BaseAbstractModelQuerySet
from django.db import models, transaction
from django.utils import timezone
from notification.models.base import (
    NotificationHistoryBase,
    NotificationHistoryQuerySet,
    NotificationHistorySentToBase,
    NotificationTemplateBase,
)
from user.models import UserExt

_KAKAO_VAR_RE = re_compile(r"#\{(\w+)\}")
_NHN_APPROVED_STATUS = "TSC03"
_READ_ONLY_MSG = (
    "NHN Cloud 알림톡 템플릿은 NHN Cloud Console에서 관리되므로 로컬에서 직접 생성/수정/삭제할 수 없습니다. "
    "외부 변경사항을 반영하려면 sync_with_nhn_cloud()를 사용하세요."
)


class NHNCloudKakaoAlimTalkNotificationTemplateQuerySet(BaseAbstractModelQuerySet):
    def create(self, *args: Any, **kwargs: Any) -> models.Model:
        raise NotImplementedError(_READ_ONLY_MSG)

    def bulk_create(self, *args: Any, **kwargs: Any) -> list[models.Model]:
        raise NotImplementedError(_READ_ONLY_MSG)

    def update(self, *args: Any, **kwargs: Any) -> int:
        raise NotImplementedError(_READ_ONLY_MSG)

    def delete(self) -> int:  # type: ignore[override]
        raise NotImplementedError(_READ_ONLY_MSG)

    def sync_with_nhn_cloud(self) -> Self:
        sender_keys = [s["senderKey"] for s in nhn_cloud_kakao_alimtalk_client.get_sender_list()["senders"]]
        external_payloads = []
        for sk in sender_keys:
            response = nhn_cloud_kakao_alimtalk_client.list_templates(sender_key=sk, pageSize=1000)
            external_payloads.extend(response["templateListResponse"]["templates"])

        external_by_code = {t["templateCode"]: t for t in external_payloads if t["status"] == _NHN_APPROVED_STATUS}
        local_by_code = {t.code: t for t in self.filter_active()}

        with transaction.atomic():
            # 차단되지 않는 부모 queryset 인스턴스. bulk_update 내부의 `queryset.filter(...).update()`도
            # `_clone`이 `self.__class__`를 보존하므로 본 클래스의 차단을 우회하려면 부모 인스턴스를 사용해야 함.
            unblocked = BaseAbstractModelQuerySet(model=self.model)
            now, system_user = timezone.now(), UserExt.get_system_user()

            unblocked.bulk_create(
                [
                    NHNCloudKakaoAlimTalkNotificationTemplate(
                        code=code,
                        title=ext["templateName"],
                        description="",
                        sent_from=ext["senderKey"],
                        data=default_json_dumps(ext),
                        created_by=system_user,
                        updated_by=system_user,
                    )
                    for code, ext in external_by_code.items()
                    if code not in local_by_code
                ],
            )

            updated_rows = []
            for code, ext in external_by_code.items():
                if (row := local_by_code.get(code)) is None:
                    continue

                new_data = default_json_dumps(ext)
                if row.title != ext["templateName"] or row.sent_from != ext["senderKey"] or row.data != new_data:
                    row.title = ext["templateName"]
                    row.sent_from = ext["senderKey"]
                    row.data = new_data
                    row.updated_at = now
                    row.updated_by = system_user
                    updated_rows.append(row)
            unblocked.bulk_update(
                updated_rows,
                fields=["title", "sent_from", "data", "updated_at", "updated_by"],
                batch_size=100,
            )

            unblocked.filter(id__in=[r.id for c, r in local_by_code.items() if c not in external_by_code]).delete()

        return self.filter_active()


class NHNCloudKakaoAlimTalkNotificationTemplate(NotificationTemplateBase):
    variable_start: ClassVar[str] = "#{"
    variable_end: ClassVar[str] = "}"
    html_template_name: ClassVar[str] = "nhn_cloud_kakao_alimtalk_preview.html"

    objects: NHNCloudKakaoAlimTalkNotificationTemplateQuerySet = (
        NHNCloudKakaoAlimTalkNotificationTemplateQuerySet.as_manager()  # type: ignore[misc, assignment]
    )

    def save(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError(_READ_ONLY_MSG)

    def delete(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError(_READ_ONLY_MSG)

    @classmethod
    def _to_dtl(cls, source: str) -> str:
        return _KAKAO_VAR_RE.sub(r"{{ \1 }}", source)


class NHNCloudKakaoAlimTalkNotificationHistorySentTo(NotificationHistorySentToBase):
    history = models.ForeignKey(
        "NHNCloudKakaoAlimTalkNotificationHistory",
        on_delete=models.PROTECT,
        related_name="sent_to_list",
    )

    @property
    def payload(self) -> dict[str, Any]:
        # Kakao 외부 API는 templateParameter dict를 그대로 받으므로 로컬 render 없이 self.context 사용.
        # (render() 자체는 admin 미리보기용으로만 사용됨.)
        return self.context


class NHNCloudKakaoAlimTalkNotificationHistoryQuerySet(
    NotificationHistoryQuerySet["NHNCloudKakaoAlimTalkNotificationHistory", NHNCloudKakaoAlimTalkNotificationTemplate],
):
    pass


class NHNCloudKakaoAlimTalkNotificationHistory(NotificationHistoryBase):
    client: ClassVar[NHNCloudKakaoAlimTalkClient] = nhn_cloud_kakao_alimtalk_client
    template_class: ClassVar[type[NHNCloudKakaoAlimTalkNotificationTemplate]] = (
        NHNCloudKakaoAlimTalkNotificationTemplate
    )
    sent_to_class: ClassVar[type[NHNCloudKakaoAlimTalkNotificationHistorySentTo]] = (
        NHNCloudKakaoAlimTalkNotificationHistorySentTo
    )

    template = models.ForeignKey(
        NHNCloudKakaoAlimTalkNotificationTemplate,
        on_delete=models.PROTECT,
        related_name="histories",
    )

    objects: NHNCloudKakaoAlimTalkNotificationHistoryQuerySet = (
        NHNCloudKakaoAlimTalkNotificationHistoryQuerySet.as_manager()  # type: ignore[misc, assignment]
    )
