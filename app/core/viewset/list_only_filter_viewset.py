from django.db.models.query import QuerySet
from rest_framework import viewsets


class ListOnlyFilterMixin(viewsets.GenericViewSet):
    """목록용 필터를 list action 에만 적용한다.

    DRF 의 get_object() 는 filter_queryset() 을 거치므로, 목록 기본 스코프
    (EventFilterMixin 의 "최신 이벤트" 등)가 단건 조회까지 좁혀 PK 가 유효한데도
    404 가 난다. 단건 조회는 PK 로 지목하는 영구 링크이므로 스코프 밖이어도 접근 가능해야 한다.
    """

    def filter_queryset(self, queryset: QuerySet) -> QuerySet:
        if self.action != "list":
            return queryset

        return super().filter_queryset(queryset)
