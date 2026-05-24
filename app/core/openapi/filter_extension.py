from drf_spectacular.contrib.django_filters import DjangoFilterExtension as _BaseDjangoFilterExtension


class DjangoFilterExtension(_BaseDjangoFilterExtension):
    """기본 확장은 DB 비용 우려로 callable `choices` 를 무시한다.

    Filter 클래스에 `expose_callable_choices_in_schema = True` 를 붙이면 스키마 생성 시
    한 번만 호출해 enum 으로 노출. 런타임 dynamism 은 유지하면서 OpenAPI 문서에도
    선택지를 드러내고 싶을 때 사용.
    """

    priority = 1

    def _get_explicit_filter_choices(self, filter_field):  # type: ignore[no-untyped-def]
        choices = filter_field.extra.get("choices")
        if callable(choices) and getattr(filter_field, "expose_callable_choices_in_schema", False):
            try:
                resolved = list(choices())
            except Exception:
                return []
            return [c for c, _ in resolved]
        return super()._get_explicit_filter_choices(filter_field)
