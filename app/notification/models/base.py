from enum import StrEnum, auto
from json import loads as json_loads
from logging import getLogger
from typing import TYPE_CHECKING, Any, ClassVar, Generic, NotRequired, TypedDict, TypeVar
from uuid import uuid4

from core.external_apis.__interface__ import NotificationServiceInterface, SendParameters
from core.models import BaseAbstractModel, BaseAbstractModelQuerySet
from django.db import models, transaction
from django.template import Context, Template
from django.template.base import VariableNode
from django.template.loader import get_template

if TYPE_CHECKING:
    from django.db.models.manager import RelatedManager

slack_logger = getLogger("slack_logger")


class UnhandledVariableHandling(StrEnum):
    RAISE = auto()
    RANDOM = auto()
    SHOW_AS_TEMPLATE_VAR = auto()
    REMOVE = auto()


class NotificationStatus(models.TextChoices):
    CREATED = "CREATED"
    SENDING = "SENDING"
    SENT = "SENT"
    FAILED = "FAILED"


class Recipient(TypedDict):
    recipient: str
    context: NotRequired[dict[str, Any]]


def _walk_strings(value: Any, fn: Any) -> Any:
    # JSON 트리 안의 string node에만 fn을 적용. dict key와 non-string scalar는 그대로 보존.
    if isinstance(value, str):
        return fn(value)
    if isinstance(value, dict):
        return {k: _walk_strings(v, fn) for k, v in value.items()}
    if isinstance(value, list):
        return [_walk_strings(v, fn) for v in value]
    return value


class NotificationTemplateBase(BaseAbstractModel):
    variable_start: ClassVar[str] = "{{"
    variable_end: ClassVar[str] = "}}"
    html_template_name: ClassVar[str]

    code = models.CharField(max_length=128)
    title = models.CharField(max_length=256, db_index=True)
    description = models.TextField(null=True, blank=True)
    data = models.TextField()

    # Email: from address, SMS: 발신번호, Kakao: sender key
    sent_from = models.CharField(max_length=256)

    class Meta:
        abstract = True
        constraints = [
            models.UniqueConstraint(
                fields=["code"],
                condition=models.Q(deleted_at__isnull=True),
                name="uq_%(app_label)s_%(class)s_code",
            ),
            models.UniqueConstraint(
                fields=["code", "title"],
                condition=models.Q(deleted_at__isnull=True),
                name="uq_%(app_label)s_%(class)s_code_title",
            ),
        ]

    @classmethod
    def _to_dtl(cls, source: str) -> str:
        return source

    @classmethod
    def _extract_root_variables(cls, source: str) -> set[str]:
        roots: set[str] = set()
        for node in Template(cls._to_dtl(source)).nodelist.get_nodes_by_type(VariableNode):
            var = node.filter_expression.var
            if not hasattr(var, "literal") or var.literal is not None:
                continue
            roots.add(str(var.var).split(".", 1)[0])
        return roots

    @property
    def template_variables(self) -> set[str]:
        # template_data를 JSON 트리로 파싱한 뒤 모든 string value에서 변수를 수집해 union.
        # template_data가 유효한 JSON이 아니면 단일 문자열로 처리.
        try:
            parsed = json_loads(self.data)
        except ValueError:
            return type(self)._extract_root_variables(self.data)

        all_vars: set[str] = set()

        def collect(s: str) -> str:
            all_vars.update(type(self)._extract_root_variables(s))
            return s

        _walk_strings(parsed, collect)
        return all_vars

    def build_preview_sent_to(self, context: dict[str, Any]) -> "NotificationHistorySentToBase":
        # admin 미리보기용 transient (unsaved) 객체 — 발송 path와 동일한 SentTo.render 경로 사용.
        # template→history reverse relation에서 채널의 History 클래스 동적 dispatch.
        history_class: type[NotificationHistoryBase] = type(self)._meta.get_field("histories").related_model
        history = history_class(template=self, template_data=self.data, sent_from=self.sent_from)
        return history.sent_to_class(history=history, context=context)


THistory = TypeVar("THistory", bound="NotificationHistoryBase")
TTemplate = TypeVar("TTemplate", bound=NotificationTemplateBase)


class NotificationHistoryQuerySet(BaseAbstractModelQuerySet, Generic[THistory, TTemplate]):
    @transaction.atomic
    def create_for_recipients(self, *, template: TTemplate, recipients: list[Recipient]) -> THistory:
        # template은 항상 필수. templateless 발송 시 호출자가 unsaved 인스턴스를 구성해 전달.
        # 저장된 template만 FK로 연결, snapshot은 template.data/sent_from에서 추출.
        if not template.data or not template.sent_from:
            raise ValueError("template.data와 template.sent_from이 모두 필요합니다.")

        history: THistory = self.create(
            # unsaved (transient) template은 FK로 연결하지 않음 — id가 default uuid4로 채워지므로 _state.adding으로 판별.
            template=None if template._state.adding else template,
            template_data=template.data,
            sent_from=template.sent_from,
        )

        sent_to_class = self.model.sent_to_class
        sent_to_class.objects.bulk_create([sent_to_class(history=history, **r) for r in recipients])
        return history


class NotificationHistoryBase(BaseAbstractModel):
    client: ClassVar[NotificationServiceInterface]

    template_class: ClassVar[type[NotificationTemplateBase]]
    sent_to_class: ClassVar[type["NotificationHistorySentToBase"]]
    template_data = models.TextField()
    sent_from = models.CharField(max_length=256)

    sent_to_list: "RelatedManager[NotificationHistorySentToBase]"

    class Meta:
        abstract = True

    @property
    def template_code(self) -> str:
        return self.template.code if self.template_id else ""

    @property
    def sent_to_status_summary(self) -> dict[str, int]:
        # prefetch된 sent_to_list가 있으면 in-memory 집계 (list 엔드포인트에서 history 당 GROUP BY 회피),
        # 없으면 GROUP BY 한 번으로 카운트.
        prefetched = getattr(self, "_prefetched_objects_cache", {})
        if "sent_to_list" in prefetched:
            counts: dict[str, int] = {}
            for s in self.sent_to_list.all():
                counts[s.status] = counts.get(s.status, 0) + 1
        else:
            counts = dict(self.sent_to_list.values("status").annotate(n=models.Count("*")).values_list("status", "n"))
        return {status.value.lower(): counts.get(status.value, 0) for status in NotificationStatus}

    @transaction.atomic
    def _dispatch(self, sent_to_qs: "models.QuerySet[NotificationHistorySentToBase]") -> None:
        from notification.tasks import send_notification_to_recipient

        if not (sent_to_ids := list(sent_to_qs.values_list("id", flat=True))):
            return
        label = type(self).sent_to_class._meta.label_lower
        transaction.on_commit(lambda: [send_notification_to_recipient.delay(label, sid) for sid in sent_to_ids])

    def send(self) -> None:
        self._dispatch(self.sent_to_list.all())

    def retry(self) -> None:
        self._dispatch(self.sent_to_list.filter(status=NotificationStatus.FAILED))


class NotificationHistorySentToBase(BaseAbstractModel):
    history: models.ForeignKey[NotificationHistoryBase]

    recipient = models.CharField(max_length=256)
    context = models.JSONField(default=dict)
    status = models.CharField(
        max_length=16,
        choices=NotificationStatus.choices,
        default=NotificationStatus.CREATED,
        db_index=True,
    )

    class Meta:
        abstract = True
        constraints = [
            models.UniqueConstraint(
                fields=["history", "recipient"],
                condition=models.Q(deleted_at__isnull=True),
                name="uq_%(app_label)s_%(class)s_history_recipient",
            ),
        ]

    def _parsed_template_data(self) -> Any:
        try:
            return json_loads(self.history.template_data)
        except ValueError:
            return self.history.template_data

    def _required_template_variables(self, payload: Any) -> set[str]:
        template_class = self.history.template_class
        all_vars: set[str] = set()
        _walk_strings(payload, lambda s: all_vars.update(template_class._extract_root_variables(s)) or s)
        return all_vars

    def assert_context_complete(self) -> None:
        # render()를 거치지 않는 채널(예: Kakao templateParameter)에서도 외부 호출 전에 fail-fast 보장.
        missing = self._required_template_variables(self._parsed_template_data()) - self.context.keys()
        if missing:
            raise ValueError(
                f"Notification (template_code={self.history.template_code or '-'}) rendered "
                f"without required context variables: {sorted(missing)}",
            )

    def render(self, undef_var: UnhandledVariableHandling = UnhandledVariableHandling.RAISE) -> dict[str, Any]:
        # template_data를 JSON으로 먼저 파싱한 뒤 string value에만 Django Template을 적용 →
        # context가 JSON-special char(`"`, `\`, 줄바꿈 등)를 포함해도 결과 JSON 구조가 깨지지 않음.
        # autoescape=False — 외부 채널(SMS, Kakao templateParameter)은 raw text 기대. HTML escape이 필요한 경우는
        # template 작성자가 명시적으로 |escape 필터를 사용해야 함.
        template_class = self.history.template_class
        payload = self._parsed_template_data()

        rendered_context = dict(self.context)
        missing = self._required_template_variables(payload) - rendered_context.keys()

        if missing and undef_var is UnhandledVariableHandling.RAISE:
            raise ValueError(
                f"Notification (template_code={self.history.template_code or '-'}) rendered "
                f"without required context variables: {sorted(missing)}",
            )

        for key in missing:
            match undef_var:
                case UnhandledVariableHandling.SHOW_AS_TEMPLATE_VAR:
                    rendered_context[key] = f"{template_class.variable_start} {key} {template_class.variable_end}"
                case UnhandledVariableHandling.RANDOM:
                    rendered_context[key] = f"RandomValue-{uuid4().hex[:8]}"
                case UnhandledVariableHandling.REMOVE:
                    rendered_context[key] = ""

        ctx = Context(rendered_context, autoescape=False)
        return _walk_strings(payload, lambda s: Template(template_class._to_dtl(s)).render(ctx))

    def render_as_html(self, undef_var: UnhandledVariableHandling = UnhandledVariableHandling.RANDOM) -> str:
        return get_template(self.history.template_class.html_template_name).render(self.render(undef_var=undef_var))

    @property
    def payload(self) -> dict[str, Any]:
        # 채널별 외부 API에 보낼 payload — 기본은 snapshot template + context를 render한 결과.
        # Kakao처럼 raw context를 그대로 넘겨야 하면 subclass에서 override.
        return self.render()

    def build_send_parameters(self) -> SendParameters:
        return SendParameters(
            payload=self.payload,
            send_to=self.recipient,
            template_code=self.history.template_code,
            sent_from=self.history.sent_from,
        )

    def send(self) -> None:
        self.status = NotificationStatus.SENDING
        self.save(update_fields=["status"])

        try:
            self.history.client.send_message(data=self.build_send_parameters())
        except Exception:
            self.status = NotificationStatus.FAILED
            self.save(update_fields=["status"])
            slack_logger.exception(
                "Notification send failed: history_id=%s template_code=%s recipient=%s",
                self.history.id,
                self.history.template_code,
                self.recipient,
            )
            raise

        self.status = NotificationStatus.SENT
        self.save(update_fields=["status"])
