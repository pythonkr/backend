from __future__ import annotations

from admin_api.serializers.event.timetable import TimetableAdminSerializer, timetable_version
from core.authz import IsSuperUser
from core.const.tag import OpenAPITag
from drf_spectacular.utils import extend_schema
from event.models import Event
from rest_framework import status, viewsets
from rest_framework.request import Request
from rest_framework.response import Response


class EventPresentationTimetableAdminViewSet(viewsets.GenericViewSet):
    permission_classes = [IsSuperUser]
    serializer_class = TimetableAdminSerializer
    queryset = Event.objects.filter_active()

    @extend_schema(tags=[OpenAPITag.ADMIN_EVENT_PRESENTATION])
    def retrieve(self, request: Request, *args, **kwargs) -> Response:
        event = self.get_object()
        return Response(
            data=self.get_serializer(event).data if request.method == "GET" else None,
            status=status.HTTP_200_OK,
            headers={"ETag": f'"{timetable_version(event)}"'},
        )

    @extend_schema(tags=[OpenAPITag.ADMIN_EVENT_PRESENTATION])
    def update(self, request: Request, *args, **kwargs) -> Response:
        event = self.get_object()
        current = timetable_version(event)

        if_match = request.headers.get("If-Match")
        if if_match is not None and if_match.strip('"') != current:
            return Response(
                data=self.get_serializer(event).data,
                status=status.HTTP_412_PRECONDITION_FAILED,
                headers={"ETag": f'"{current}"'},
            )

        patch = TimetableAdminSerializer(data=request.data, context={"event": event})
        patch.is_valid(raise_exception=True)
        patch.save()

        return Response(
            data=self.get_serializer(event).data,
            status=status.HTTP_200_OK,
            headers={"ETag": f'"{timetable_version(event)}"'},
        )
