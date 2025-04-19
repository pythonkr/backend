from django.db import models
import uuid

class Page(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    is_active = models.BooleanField(default=False)
    css = models.TextField(null=True, blank=True, default=None)
    title = models.CharField(max_length=256)
    subtitle = models.CharField(max_length=512)

    def __str__(self):
        return f"{self.title}"

class Sitemap(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parent_sitemap = models.ForeignKey('self', null=True, blank=True, default=None, on_delete=models.SET_NULL, related_name='children')
    name = models.CharField(max_length=256)
    order = models.IntegerField(default=0)
    page = models.ForeignKey(Page, on_delete=models.PROTECT)
    display_start_at = models.DateTimeField(null=True, blank=True)
    display_end_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.name}"

class Section(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    page = models.ForeignKey(Page, on_delete=models.CASCADE)
    order = models.IntegerField(default=0)
    css = models.TextField(null=True, blank=True, default=None)
    body = models.TextField(help_text='Content of the page, Written in markdown format')

    def __str__(self):
        return f"Section {self.order} of {self.page}"