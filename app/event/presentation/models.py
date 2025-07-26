from __future__ import annotations

import datetime
import uuid
from contextlib import suppress
from typing import Self

from core.models import BaseAbstractModel, BaseAbstractModelQuerySet, MarkdownField
from django.contrib.auth import get_user_model
from django.db import models
from event.models import Event
from file.models import PublicFile

User = get_user_model()


class PresentationQuerySet(BaseAbstractModelQuerySet):
    def get_all_nested_data(self):
        return (
            self.filter_active()
            .prefetch_related(
                models.Prefetch(
                    lookup="categories",
                    queryset=PresentationCategory.objects.filter_active(),
                    to_attr="_prefetched_active_categories",
                ),
                models.Prefetch(
                    lookup="speakers",
                    queryset=PresentationSpeaker.objects.filter_active().select_related("user", "image"),
                    to_attr="_prefetched_active_speakers",
                ),
                models.Prefetch(
                    lookup="roomschedule_set",
                    queryset=RoomSchedule.objects.filter_active().select_related("room", "room__event"),
                    to_attr="_prefetched_active_room_schedules",
                ),
                models.Prefetch(
                    lookup="call_for_presentation_schedules",
                    queryset=CallForPresentationSchedule.objects.filter_active().select_related("presentation_type"),
                    to_attr="_prefetched_active_call_for_presentation_schedules",
                ),
            )
            .select_related("image")
        )


class PresentationType(BaseAbstractModel):
    event = models.ForeignKey(Event, on_delete=models.PROTECT)
    name = models.CharField(max_length=256)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "name"],
                name="uq__prst_type__event__name",
                condition=models.Q(deleted_at__isnull=True),
            ),
        ]

    def __str__(self) -> str:
        return f"[{self.event.name}] {self.name}"


class PresentationCategory(BaseAbstractModel):
    type = models.ForeignKey(PresentationType, on_delete=models.PROTECT)
    name = models.CharField(max_length=256)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["type", "name"],
                name="uq__prst_cat__type__name",
                condition=models.Q(deleted_at__isnull=True),
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Presentation(BaseAbstractModel):
    type = models.ForeignKey(PresentationType, on_delete=models.PROTECT)
    title = models.CharField(max_length=256)
    summary = models.TextField(blank=True, default="")
    description = MarkdownField(blank=True, default="")
    image = models.ForeignKey(PublicFile, on_delete=models.PROTECT, null=True, blank=True)
    slideshow_url = models.URLField(null=True, blank=True, default="")

    categories = models.ManyToManyField(to="PresentationCategory", through="PresentationCategoryRelation")
    objects: PresentationQuerySet = PresentationQuerySet.as_manager()

    def __str__(self) -> str:
        return f"[{self.type.name}] {self.title}"

    def active_categories(self) -> list[PresentationCategory]:
        with suppress(AttributeError):
            return self._prefetched_active_categories
        return list(self.categories.filter_active())

    def active_speakers(self) -> list[PresentationSpeaker]:
        with suppress(AttributeError):
            return self._prefetched_active_speakers
        return list(self.speakers.filter_active())


class PresentationCategoryRelation(models.Model):
    presentation = models.ForeignKey(Presentation, on_delete=models.CASCADE)
    category = models.ForeignKey(PresentationCategory, on_delete=models.CASCADE)


class PresentationSpeaker(BaseAbstractModel):
    presentation = models.ForeignKey(Presentation, on_delete=models.PROTECT, related_name="speakers")
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    image = models.ForeignKey(PublicFile, on_delete=models.PROTECT, null=True, blank=True)
    biography = MarkdownField(blank=True, default="")


class CallForPresentationSchedule(BaseAbstractModel):
    presentation_type = models.ForeignKey(PresentationType, on_delete=models.PROTECT)
    presentation = models.ForeignKey(
        Presentation, on_delete=models.PROTECT, related_name="call_for_presentation_schedules", null=True, blank=True
    )
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    next_call_for_presentation_schedule = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True)


class Room(BaseAbstractModel):
    event = models.ForeignKey(Event, on_delete=models.PROTECT)
    name = models.CharField(max_length=256)

    def __str__(self) -> str:
        return f"[{self.event.name}] {self.name}"


class RoomScheduleQuerySet(BaseAbstractModelQuerySet):
    def filter_conflict(self, room: Room | uuid.UUID | str, start: datetime.datetime, end: datetime.datetime) -> Self:
        qs = self

        if isinstance(room, (uuid.UUID, str)):
            qs = qs.filter(room_id=room)
        elif isinstance(room, Room):
            qs = qs.filter(room=room)

        return qs.filter(start_at__lt=end, end_at__gt=start)


class RoomSchedule(BaseAbstractModel):
    room = models.ForeignKey(Room, on_delete=models.PROTECT)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    presentation = models.ForeignKey(Presentation, on_delete=models.PROTECT)

    objects: RoomScheduleQuerySet = RoomScheduleQuerySet.as_manager()

    def __str__(self) -> str:
        return f"[{self.room}] {self.start_at} - {self.end_at} ({self.presentation})"
