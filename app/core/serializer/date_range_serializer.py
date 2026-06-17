from datetime import date, datetime, time, timedelta

from core.const.datetime import KST
from rest_framework import serializers


class DateRangeSerializer(serializers.Serializer):
    date_from = serializers.DateField()
    date_to = serializers.DateField()

    def validate_date_from(self, value: date) -> datetime:
        return datetime.combine(value, time.min, tzinfo=KST)

    def validate_date_to(self, value: date) -> datetime:
        return datetime.combine(value + timedelta(days=1), time.min, tzinfo=KST)

    def validate(self, attrs: dict) -> dict:
        # date_to 는 exclusive end 로 +1d 보정된 값 — 정상 구간이면 from < to.
        if attrs["date_from"] >= attrs["date_to"]:
            raise serializers.ValidationError("date_to 는 date_from 이후여야 합니다.")
        return attrs
