from core.const.tag import OpenAPITag
from core.viewset.list_only_filter_viewset import ListOnlyFilterMixin
from django.db.models.query import QuerySet
from django.shortcuts import get_object_or_404
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
from rest_framework import exceptions, mixins, permissions, request, response, status, viewsets


@method_decorator(name="list", decorator=extend_schema(tags=[OpenAPITag.EVENT_PRESENTATION]))
class PresentationCategoryViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = PresentationCategory.objects.filter_active()
    serializer_class = PresentationCategorySerializer


@method_decorator(name="list", decorator=extend_schema(tags=[OpenAPITag.EVENT_PRESENTATION]))
@method_decorator(name="retrieve", decorator=extend_schema(tags=[OpenAPITag.EVENT_PRESENTATION]))
class PresentationViewSet(
    ListOnlyFilterMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Presentation.objects.get_all_nested_data()
    serializer_class = PresentationSerializer
    filterset_class = PresentationFilterSet


@extend_schema(tags=[OpenAPITag.EVENT_PRESENTATION_BOOKMARK])
class PresentationBookmarkViewSet(viewsets.GenericViewSet):
    queryset = PresentationBookmark.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PresentationBookmarkRequestSerializer
    lookup_field = "presentation_id"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        get_object_or_404(Event, id=self.kwargs["event_id"])

    def get_queryset(self) -> QuerySet:
        return (
            super().get_queryset().filter(user=self.request.user, presentation__type__event_id=self.kwargs["event_id"])
        )

    def destroy(self, request: request.Request, **kwargs) -> response.Response:
        presentation_id = self.kwargs["presentation_id"]
        if not Presentation.objects.filter(id=presentation_id, deleted_at__isnull=True).exists():
            raise exceptions.NotFound("해당 세션 정보가 없습니다.")
        self.get_queryset().filter(presentation_id=presentation_id).delete()
        return response.Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        summary="북마크 목록 조회",
        parameters=[],
        responses={
            status.HTTP_200_OK: PresentationBookmarkListResponseSerializer,
            status.HTTP_401_UNAUTHORIZED: ErrorResponse401Serializer,
            status.HTTP_404_NOT_FOUND: ErrorResponse404Serializer,
        },
    )
    def list(self, request: request.Request, **kwargs) -> response.Response:
        queryset = self.get_queryset()
        presentation_ids = list(queryset.values_list("presentation_id", flat=True))
        return response.Response({"presentation_ids": presentation_ids})

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
    def create(self, request: request.Request, **kwargs) -> response.Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance, created = serializer.create(serializer.validated_data)
        serializer.save()

        return response.Response(
            {"presentation_id": str(instance.presentation_id)},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
