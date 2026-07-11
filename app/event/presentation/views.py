from core.const.tag import OpenAPITag
from django.db.models import Q
from django.utils.decorators import method_decorator
from drf_spectacular.utils import extend_schema
from drf_standardized_errors.openapi_serializers import (
    ErrorResponse401Serializer,
    ErrorResponse404Serializer,
)
from event.models import Event
from event.presentation.filters import PresentationFilterSet
from event.presentation.models import Presentation, PresentationBookmark, PresentationCategory
from event.presentation.serializers import (
    PresentationBookmarkListResponseSerializer,
    PresentationBookmarkRequestSerializer,
    PresentationBookmarkResponseSerializer,
    PresentationCategorySerializer,
    PresentationSerializer,
)
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response


@method_decorator(name="list", decorator=extend_schema(tags=[OpenAPITag.EVENT_PRESENTATION]))
class PresentationCategoryViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = PresentationCategory.objects.filter_active()
    serializer_class = PresentationCategorySerializer


@method_decorator(name="list", decorator=extend_schema(tags=[OpenAPITag.EVENT_PRESENTATION]))
@method_decorator(name="retrieve", decorator=extend_schema(tags=[OpenAPITag.EVENT_PRESENTATION]))
class PresentationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Presentation.objects.get_all_nested_data()
    serializer_class = PresentationSerializer
    filterset_class = PresentationFilterSet


@extend_schema(tags=[OpenAPITag.EVENT_PRESENTATION_BOOKMARK])
class PresentationBookmarkViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PresentationBookmarkRequestSerializer

    def _resolve_event(self, request: Request) -> Event:
        event_name = request.query_params.get("event")
        if not event_name:
            event = Event.objects.filter_active().first()
            if not event:
                raise NotFound("해당 행사 정보가 없습니다.")
            return event

        event = Event.objects.filter_active().filter(Q(name_ko=event_name) | Q(name_en=event_name)).first()
        if not event:
            raise NotFound("해당 행사 정보가 없습니다.")
        return event

    @extend_schema(
        summary="북마크 목록 조회",
        parameters=[],
        responses={
            status.HTTP_200_OK: PresentationBookmarkListResponseSerializer,
            status.HTTP_401_UNAUTHORIZED: ErrorResponse401Serializer,
            status.HTTP_404_NOT_FOUND: ErrorResponse404Serializer,
        },
    )
    def list(self, request: Request) -> Response:
        event = self._resolve_event(request)
        presentation_ids = list(
            PresentationBookmark.objects.filter(user=request.user, event=event).values_list(
                "presentation_id", flat=True
            )
        )
        return Response({"presentation_ids": presentation_ids})

    @extend_schema(
        summary="북마크 추가",
        request=PresentationBookmarkRequestSerializer,
        responses={
            status.HTTP_201_CREATED: PresentationBookmarkResponseSerializer,
            status.HTTP_200_OK: PresentationBookmarkResponseSerializer,
            status.HTTP_401_UNAUTHORIZED: ErrorResponse401Serializer,
            status.HTTP_404_NOT_FOUND: ErrorResponse404Serializer,
        },
    )
    def create(self, request: Request) -> Response:
        serializer = PresentationBookmarkRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        presentation_id = serializer.validated_data["presentation_id"]

        presentation = Presentation.objects.filter_active().filter(id=presentation_id).first()
        if not presentation:
            raise NotFound("해당 세션 정보가 없습니다.")

        event = presentation.type.event
        _, created = PresentationBookmark.objects.get_or_create(
            user=request.user,
            presentation=presentation,
            defaults={"event": event},
        )
        return Response(
            {"presentation_id": str(presentation.id)},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @extend_schema(
        summary="북마크 삭제",
        responses={
            status.HTTP_204_NO_CONTENT: None,
            status.HTTP_401_UNAUTHORIZED: ErrorResponse401Serializer,
            status.HTTP_404_NOT_FOUND: ErrorResponse404Serializer,
        },
    )
    def destroy(self, request: Request, pk: str = None) -> Response:
        presentation = Presentation.objects.filter_active().filter(id=pk).first()
        if not presentation:
            raise NotFound("해당 세션 정보가 없습니다.")

        PresentationBookmark.objects.filter(user=request.user, presentation=presentation).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
