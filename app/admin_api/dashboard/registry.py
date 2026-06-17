from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, NotRequired, TypedDict, Unpack

from core.serializer.date_range_serializer import DateRangeSerializer
from django.urls import reverse
from rest_framework import serializers
from rest_framework.fields import empty


@dataclass(frozen=True)
class ChartHandler:
    id: str
    title: str
    type: str  # line | bar | pie | metric
    params_serializer: type  # DRF Serializer — 요청 검증 + 정의(params) 역생성의 단일 소스
    handle: Callable[[Any], dict]  # params -> ChartDataResponse(부분) dict
    unit: str | None = None
    options: dict | None = None

    def to_dict(self, dynamic_options: dict[str, list[dict]]) -> dict:
        """차트 정의 응답 dict — 자기 data 엔드포인트/파라미터(serializer 역생성)를 직접 포함."""
        return {
            "id": self.id,
            "title": self.title,
            "type": self.type,
            "unit": self.unit,
            "options": self.options,
            "endpoint": reverse("v1:admin-dashboard-chart-data", kwargs={"pk": self.id}),
            "method": "POST",
            "params": _param_definitions(self.params_serializer, dynamic_options),
        }


class ChartFields(TypedDict):
    id: str
    title: str
    type: str
    params_serializer: type
    unit: NotRequired[str | None]
    options: NotRequired[dict | None]


CHART_REGISTRY: dict[str, ChartHandler] = {}


def chart(**fields: Unpack[ChartFields]) -> Callable[[Callable[[Any], dict]], Callable[[Any], dict]]:
    def decorator(handle: Callable[[Any], dict]) -> Callable[[Any], dict]:
        handler = ChartHandler(**fields, handle=handle)
        if handler.id in CHART_REGISTRY:
            raise ValueError(f"중복 chart_id: {handler.id}")
        CHART_REGISTRY[handler.id] = handler
        return handle

    return decorator


# --- 파라미터 정의 역생성 (params serializer 필드 → 프론트 정의) ---
# DRF 필드 클래스 → 프론트 파라미터 type. 위에서부터 먼저 매칭(다중선택을 단일선택보다 먼저).
_PARAM_TYPE_BY_FIELD = (
    (DateRangeSerializer, "date_range"),
    ((serializers.MultipleChoiceField, serializers.ListField), "multi_select"),
    (serializers.ChoiceField, "select"),
    (serializers.BooleanField, "boolean"),
    ((serializers.IntegerField, serializers.FloatField), "number"),
)


def _param_type(field: serializers.Field) -> str:
    if explicit := getattr(field, "param_type", None):  # 필드가 직접 지정한 type 우선
        return explicit
    for field_cls, param_type in _PARAM_TYPE_BY_FIELD:
        if isinstance(field, field_cls):
            return param_type
    return "text"


def _param_options(field: serializers.Field, dynamic_options: dict[str, list[dict]]) -> list[dict] | None:
    if source := getattr(field, "dynamic_options", None):
        return dynamic_options.get(source, [])
    if isinstance(field, serializers.ChoiceField):
        return [{"value": value, "label": label} for value, label in field.choices.items()]
    return None


def _param_definitions(serializer_class: type, dynamic_options: dict[str, list[dict]]) -> list[dict]:
    definitions = []
    for key, field in serializer_class().fields.items():
        definitions.append(
            {
                "key": key,
                "label": str(field.label) if field.label else key,
                "type": _param_type(field),
                "required": field.required,
                "default": None if field.default is empty else field.default,
                "options": _param_options(field, dynamic_options),
            }
        )
    return definitions
