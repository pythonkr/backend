from enum import StrEnum, auto
from json import loads as json_loads
from logging import getLogger
from typing import Any, ClassVar
from uuid import uuid4

from core.external_apis.__interface__ import NotificationServiceInterface, SendParameters
from core.models import BaseAbstractModel
from django.db import models
from django.template import Context, Template
from django.template.base import VariableNode
from django.template.loader import get_template

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


class NotificationTemplateBase(BaseAbstractModel):
    variable_start: ClassVar[str] = "{{"
    variable_end: ClassVar[str] = "}}"
    html_template_name: ClassVar[str]

    code = models.CharField(max_length=128)
    title = models.CharField(max_length=256, db_index=True)
    description = models.TextField(null=True, blank=True)
    data = models.TextField()

    class Meta:
        abstract = True

    def _to_dtl(self, source: str) -> str:
        return source

    @staticmethod
    def _extract_root_variables(template: Template) -> set[str]:
        roots: set[str] = set()
        for node in template.nodelist.get_nodes_by_type(VariableNode):
            var = node.filter_expression.var
            if not hasattr(var, "literal") or var.literal is not None:
                continue
            roots.add(str(var.var).split(".", 1)[0])
        return roots

    @property
    def template_variables(self) -> set[str]:
        return self._extract_root_variables(Template(self._to_dtl(self.data)))

    def render(
        self,
        context: dict[str, str],
        undefined_variable_handling: UnhandledVariableHandling = UnhandledVariableHandling.RAISE,
    ) -> dict[str, Any]:
        template = Template(self._to_dtl(self.data))
        context = dict(context)
        missing = self._extract_root_variables(template) - context.keys()

        if missing and undefined_variable_handling is UnhandledVariableHandling.RAISE:
            raise ValueError(
                f"Template '{self.code}' rendered without required context variables: {sorted(missing)}",
            )

        for key in missing:
            match undefined_variable_handling:
                case UnhandledVariableHandling.SHOW_AS_TEMPLATE_VAR:
                    context[key] = f"{self.variable_start} {key} {self.variable_end}"
                case UnhandledVariableHandling.RANDOM:
                    context[key] = f"RandomValue-{uuid4().hex[:8]}"
                case UnhandledVariableHandling.REMOVE:
                    context[key] = ""

        return json_loads(template.render(Context(context)))

    def render_as_html(
        self,
        context: dict[str, str],
        undefined_variable_handling: UnhandledVariableHandling = UnhandledVariableHandling.RANDOM,
    ) -> str:
        rendered_context = self.render(context=context, undefined_variable_handling=undefined_variable_handling)
        return get_template(self.html_template_name).render(rendered_context)


class NotificationHistoryBase(BaseAbstractModel):
    client: ClassVar[NotificationServiceInterface]

    send_to = models.CharField(max_length=256)
    context = models.JSONField(default=dict)
    status = models.CharField(
        max_length=16,
        choices=NotificationStatus.choices,
        default=NotificationStatus.CREATED,
        db_index=True,
    )

    class Meta:
        abstract = True

    @property
    def template_code(self) -> str:
        raise NotImplementedError("Subclasses must implement template_code")

    def build_send_parameters(self) -> SendParameters:
        raise NotImplementedError("Subclasses must implement build_send_parameters")

    def send(self) -> None:
        self.status = NotificationStatus.SENDING
        self.save(update_fields=["status"])
        try:
            self.client.send_message(data=self.build_send_parameters())
        except Exception:
            self.status = NotificationStatus.FAILED
            self.save(update_fields=["status"])
            slack_logger.exception(
                "Notification send failed: history_id=%s template_code=%s send_to=%s",
                self.id,
                self.template_code,
                self.send_to,
            )
            raise
        self.status = NotificationStatus.SENT
        self.save(update_fields=["status"])
