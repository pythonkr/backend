from core.models import BaseAbstractModel, BaseAbstractModelQuerySet
from django.contrib.auth import get_user_model
from django.db import models
from event.models import Event

User = get_user_model()


class PresentationQuerySet(BaseAbstractModelQuerySet):
    def get_all_nested_data(self):
        return (
            self.filter_active()
            .select_related("presentation_type")
            .prefetch_related("presentation_speakers", "presentation_categories")
        )


class PresentationType(BaseAbstractModel):
    event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name="presentation_types", null=True, blank=True)
    name = models.CharField(max_length=256, null=True, blank=True)


class PresentationCategory(BaseAbstractModel):
    presentation_type = models.ForeignKey(
        PresentationType, on_delete=models.PROTECT, related_name="presentation_categories"
    )
    name = models.CharField(max_length=256, null=True, blank=True)


class Presentation(BaseAbstractModel):
    presentation_type = models.ForeignKey(PresentationType, on_delete=models.PROTECT, related_name="presentations")
    presentation_categories = models.ManyToManyField(to="PresentationCategory", through="PresentationCategoryRelation")

    objects: PresentationQuerySet = PresentationQuerySet.as_manager()


class PresentationCategoryRelation(models.Model):
    presentation = models.ForeignKey(Presentation, on_delete=models.CASCADE, related_name="relations")
    category = models.ForeignKey(PresentationCategory, on_delete=models.CASCADE, related_name="relations")


class PresentationSpeaker(BaseAbstractModel):
    presentation = models.ForeignKey(Presentation, on_delete=models.PROTECT, related_name="presentation_speakers")
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="presentation_speakers")
    name = models.CharField(max_length=256, null=True, blank=True)
    biography = models.CharField(max_length=256, null=True, blank=True)
