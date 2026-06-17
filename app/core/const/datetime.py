from datetime import timedelta, timezone

from django.db import models

UTC = timezone.utc
KST = timezone(timedelta(hours=9))

KOREAN_WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]


class Granularity(models.TextChoices):
    HOUR = "hour", "시간"
    DAY = "day", "일"
    WEEK = "week", "주"
    MONTH = "month", "월"
