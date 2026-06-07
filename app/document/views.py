from __future__ import annotations

from contextlib import suppress
from typing import Any
from urllib.parse import quote
from uuid import UUID

from core.const.datetime import KST
from core.const.tag import OpenAPITag
from core.openapi.schemas import build_html_responses
from django.http import HttpResponse
from document.issuable import IssuableMixin
from document.models import IssuedDocument
from drf_spectacular.openapi import OpenApiParameter, OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.renderers import TemplateHTMLRenderer
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_410_GONE,
    HTTP_503_SERVICE_UNAVAILABLE,
)
from rest_framework.views import APIView


class DocumentDownloadView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [TemplateHTMLRenderer]

    @extend_schema(
        summary="발급 문서 PDF 다운로드",
        tags=[OpenAPITag.DOCUMENT],
        parameters=[OpenApiParameter(name="pk", type=OpenApiTypes.UUID, location=OpenApiParameter.PATH)],
        responses=(
            build_html_responses(names=["문서 PDF 다운로드"])
            | build_html_responses(names=["반려/무효 안내"], status_code=HTTP_400_BAD_REQUEST)
            | build_html_responses(names=["문서를 찾을 수 없는 경우"], status_code=HTTP_404_NOT_FOUND)
            | build_html_responses(names=["반려된 문서"], status_code=HTTP_410_GONE)
        ),
    )
    def get(self, request: Request, pk: UUID, *args: Any, **kwargs: Any) -> HttpResponse:
        msg, http_status = "", HTTP_200_OK
        if not (
            (document := IssuedDocument.objects.filter_active().filter(pk=pk).first())
            and isinstance(document.issuable, IssuableMixin)
            and document.issuable.is_document_downloadable_by(request.user)
        ):
            msg, http_status = "문서를 찾을 수 없습니다. 링크가 올바른지 확인하거나,", HTTP_404_NOT_FOUND
        elif document.revoked_at is not None:
            msg, http_status = "본 문서는 반려되었습니다.", HTTP_410_GONE
        if msg:
            msg += " 파이콘 준비 위원회(pyconkr@pycon.kr)로 문의해주세요."
            return Response(data={"message": msg}, status=http_status, template_name="document_verify_error.html")

        with suppress(RuntimeError):
            filename = quote(f"{document.template.get_document_type_display()}_{document.document_number}.pdf")
            return HttpResponse(
                content=document.render_pdf(),
                content_type="application/pdf",
                headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
            )

        return Response(
            data={
                "message": "문서를 생성할 수 없습니다. 잠시 후 다시 시도하거나 파이콘 준비 위원회(pyconkr@pycon.kr)로 문의해주세요."
            },
            status=HTTP_503_SERVICE_UNAVAILABLE,
            template_name="document_verify_error.html",
        )


class CertificateVerifyView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    renderer_classes = [TemplateHTMLRenderer]

    @extend_schema(
        summary="발급 문서 검증 페이지",
        tags=[OpenAPITag.DOCUMENT],
        parameters=[OpenApiParameter(name="token", type=OpenApiTypes.STR, location=OpenApiParameter.PATH)],
        responses=(
            build_html_responses(names=["검증 결과 HTML"])
            | build_html_responses(names=["반려/무효 안내"], status_code=HTTP_400_BAD_REQUEST)
            | build_html_responses(names=["문서를 찾을 수 없는 경우"], status_code=HTTP_404_NOT_FOUND)
            | build_html_responses(names=["반려된 문서"], status_code=HTTP_410_GONE)
        ),
    )
    def get(self, request: Request, token: str, *args: Any, **kwargs: Any) -> Response:
        msg, http_status = "", HTTP_200_OK
        if not (document := IssuedDocument.objects.from_verify_token(token)):
            msg, http_status = "문서를 찾을 수 없습니다. 링크가 올바른지 확인하거나,", HTTP_404_NOT_FOUND
        elif document.revoked_at is not None:
            msg, http_status = "본 문서는 반려되었습니다.", HTTP_410_GONE
        elif not isinstance(document.issuable, IssuableMixin) or not document.issuable.is_document_valid():
            msg, http_status = "문서가 유효하지 않습니다.", HTTP_400_BAD_REQUEST
        if msg:
            msg += " 파이콘 준비 위원회(pyconkr@pycon.kr)로 문의해주세요."
            return Response(data={"message": msg}, status=http_status, template_name="document_verify_error.html")

        return Response(
            data={
                "document_number": document.document_number,
                "issued_at": document.created_at.astimezone(KST).strftime("%Y-%m-%d %H:%M"),
                "fields": document.issuable.build_verify_display(document.context),
            },
            template_name="document_verify.html",
        )
