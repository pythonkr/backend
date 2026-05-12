import typing

from rest_framework import serializers


class SkipNoneListSerializer(serializers.ListSerializer):
    """child.to_representation 결과 중 None 은 결과에서 제외 — child 가 row-skip 의미론을 갖는 경우 사용."""

    def to_representation(self, data: typing.Any) -> list[typing.Any]:
        iterable = data.all() if hasattr(data, "all") else data
        return [item for item in (self.child.to_representation(o) for o in iterable) if item is not None]
