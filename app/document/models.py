from __future__ import annotations

import io
import typing
from base64 import b64encode, urlsafe_b64encode
from contextlib import suppress
from functools import cached_property
from hashlib import sha256
from hmac import new as hmac_new
from urllib.parse import urljoin

import qrcode
from core.const.datetime import KST
from core.models import BaseAbstractModel, BaseAbstractModelQuerySet
from core.util.thread_local import get_current_user
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models.functions import Now
from django.template import engines
from rest_framework.reverse import reverse
from shortuuid import decode, encode
from simple_history.models import HistoricalRecords

try:
    from weasyprint import HTML
except (ImportError, OSError):

    class HTML:
        def __init__(self, *args: typing.Any, **kwargs: typing.Any) -> None:
            pass

        def write_pdf(self, *args: typing.Any, **kwargs: typing.Any) -> bytes:
            raise RuntimeError("PDF 렌더링 환경이 준비되지 않았습니다 (WeasyPrint 시스템 라이브러리 부재).")


User = get_user_model()


class DocumentType(models.TextChoices):
    confirmation_of_participation = "confirmation_of_participation", "COP", "참가확인서"

    def __new__(cls, value: str, number_prefix: str) -> DocumentType:
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.number_prefix = number_prefix
        return obj


class DocumentTemplateQuerySet(BaseAbstractModelQuerySet):
    def get_active(self, document_type: str) -> DocumentTemplate:
        return self.filter_active().get(document_type=document_type)


class DocumentTemplate(BaseAbstractModel):
    document_type = models.CharField(max_length=50, choices=DocumentType.choices)
    body = models.TextField()

    objects: DocumentTemplateQuerySet = DocumentTemplateQuerySet.as_manager()
    history = HistoricalRecords()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["document_type"],
                condition=models.Q(deleted_at__isnull=True),
                name="uniq_active_document_template_type",
            )
        ]

    def __str__(self) -> str:
        stamp = self.created_at.date().isoformat() if self.created_at else "draft"
        return f"{self.get_document_type_display()} ({stamp})"


class IssuedDocumentQuerySet(BaseAbstractModelQuerySet):
    def for_issuable(self, issuable) -> typing.Self:
        return self.filter(
            issuable_content_type=ContentType.objects.get_for_model(issuable), issuable_object_id=issuable.pk
        )

    def from_short_id(self, short_id: str) -> IssuedDocument | None:
        # deleted(=존재하지않음) 은 제외하되 revoked(revoked_at) 은 포함 - 검증 페이지가 revoked 문서를 찾아 "취소됨" 으로 표시할 수 있어야 함.
        with suppress(ValueError):
            return self.filter_active().filter(id=decode(short_id)).first()
        return None

    def from_verify_token(self, token: str) -> IssuedDocument | None:
        try:
            prefix, short_id, salt = token.split(":")
        except ValueError:
            return None
        if prefix != "cert" or not (short_id and salt):
            return None
        if (instance := self.from_short_id(short_id)) is not None and instance.salt == salt:
            return instance
        return None


class IssuedDocument(BaseAbstractModel):
    class RevokedError(Exception):
        """이미 취소(revoke)된 문서가 있어 재발급을 막아야 하는 경우."""

    issuable_content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    issuable_object_id = models.UUIDField()
    issuable = GenericForeignKey("issuable_content_type", "issuable_object_id")

    template = models.ForeignKey(DocumentTemplate, on_delete=models.PROTECT)
    context = models.JSONField()

    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)

    objects: IssuedDocumentQuerySet = IssuedDocumentQuerySet.as_manager()  # type: ignore[assignment]
    history = HistoricalRecords()

    class Meta:
        indexes = [models.Index(fields=["issuable_content_type", "issuable_object_id"])]
        constraints = [
            # 한 issuable 당 활성(미삭제) 문서는 하나 — 동시 발급 race 로 중복 생성 방지.
            models.UniqueConstraint(
                fields=["issuable_content_type", "issuable_object_id"],
                condition=models.Q(deleted_at__isnull=True),
                name="uniq_active_issued_document_per_issuable",
            )
        ]

    if typing.TYPE_CHECKING:
        issuable_object_id: str
        template_id: str

    def __str__(self) -> str:
        return self.document_number

    @cached_property
    def short_id(self) -> str:
        return encode(self.id)

    @cached_property
    def salt(self) -> str:
        hmac_result = hmac_new(settings.DOCUMENT.verify_salt.encode(), self.id.bytes, sha256).digest()
        return urlsafe_b64encode(hmac_result).decode("utf-8").rstrip("=")

    @cached_property
    def verify_token(self) -> str:
        return f"cert:{self.short_id}:{self.salt}"

    @cached_property
    def verify_path(self) -> str:
        return reverse("v1:certificate-verify", kwargs={"token": self.verify_token})

    @property
    def document_number(self) -> str:
        year = self.created_at.year if self.created_at else "----"
        try:
            prefix = DocumentType(self.template.document_type).number_prefix
        except ValueError:
            prefix = "DOC"
        return f"{prefix}-{year}-{self.short_id}"

    def revoke(self) -> None:
        """문서를 취소(무효화)한다. deleted_at 과 분리 — 취소됨 vs 존재하지않음 을 구분하기 위함."""
        self.revoked_at = Now()  # type: ignore[assignment]
        self.revoked_by = get_current_user()
        self.save(update_fields={"revoked_at", "revoked_by"})

    def render_html(self) -> str:
        verify_url = urljoin(settings.BACKEND_DOMAIN, self.verify_path)
        qr_buffer = io.BytesIO()
        qrcode.make(verify_url).save(qr_buffer, format="PNG")
        context = self.context | {
            "document_number": self.document_number,
            "issued_at": self.created_at.astimezone(KST).strftime("%Y년 %m월 %d일"),
            "verify_url": verify_url,
            "qr_data_uri": "data:image/png;base64," + b64encode(qr_buffer.getvalue()).decode("ascii"),
        }
        return engines["django"].from_string(self.template.body).render(context)

    def render_pdf(self) -> bytes:
        return HTML(string=self.render_html()).write_pdf()
