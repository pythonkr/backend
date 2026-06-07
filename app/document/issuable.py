from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django.db import IntegrityError, models, transaction

if TYPE_CHECKING:
    from document.models import IssuedDocument
    from user.models import UserExt


class IssuableMixin:
    ISSUED_DOCUMENT_TYPE: ClassVar[str]

    class NotIssuableError(Exception):
        """is_document_valid() 조건을 충족하지 않는 issuable 에 대한 발급 시도 — 도메인 경계 가드."""

    class DocumentStatus(models.TextChoices):
        not_issuable = "not_issuable", "발급 불가"  # is_document_valid 조건 미충족
        issuable = "issuable", "발급 가능"  # 조건 충족, 아직 미발급
        issued = "issued", "발급됨"  # 유효한 발급본 존재
        revoked = "revoked", "취소됨"  # 발급본이 취소됨

    def build_document_context(self) -> dict:
        raise NotImplementedError(f"{type(self).__name__} 은 build_document_context() 를 구현해야 합니다.")

    def is_document_downloadable_by(self, user: UserExt) -> bool:
        raise NotImplementedError(f"{type(self).__name__} 은 is_document_downloadable_by() 를 구현해야 합니다.")

    def is_document_valid(self) -> bool:
        raise NotImplementedError(f"{type(self).__name__} 은 is_document_valid() 를 구현해야 합니다.")

    def build_verify_display(self, context: dict) -> dict[str, str]:
        raise NotImplementedError(f"{type(self).__name__} 은 build_verify_display() 를 구현해야 합니다.")

    def get_issued_document(self) -> IssuedDocument | None:
        # issuable 은 `issued_documents` GenericRelation 을 노출 - prefetch 로 목록 N+1 회피.
        active = [doc for doc in self.issued_documents.all() if doc.deleted_at is None]
        return max(active, key=lambda doc: doc.created_at, default=None)

    def issue_document(self) -> IssuedDocument:
        from document.models import DocumentTemplate, IssuedDocument

        if not self.is_document_valid():
            raise self.NotIssuableError(f"{type(self).__name__} 은 현재 발급 가능 상태가 아닙니다.")
        return IssuedDocument.objects.create(
            issuable=self,
            template=DocumentTemplate.objects.get_active(self.ISSUED_DOCUMENT_TYPE),
            context=self.build_document_context(),
        )

    def get_or_issue_document(self) -> IssuedDocument:
        from document.models import IssuedDocument

        if (document := self.get_issued_document()) is None:
            try:
                with transaction.atomic():
                    return self.issue_document()
            except IntegrityError:
                # 동시 발급 경쟁 — 다른 요청이 먼저 활성 문서를 만들었으니 그것을 반환(unique constraint).
                document = self.get_issued_document()
        if document is not None and document.revoked_at:
            raise IssuedDocument.RevokedError("취소된 문서입니다.")
        return document

    @property
    def document_status(self) -> str:
        if not self.is_document_valid():
            return self.DocumentStatus.not_issuable

        if not (document := self.get_issued_document()):
            return self.DocumentStatus.issuable
        return self.DocumentStatus.revoked if document.revoked_at else self.DocumentStatus.issued
