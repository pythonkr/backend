from core.admin import BaseAbstractModelAdminMixin
from django.contrib import admin
from django.http.request import HttpRequest
from django.http.response import HttpResponseNotAllowed, JsonResponse
from django.urls import re_path
from django.urls.resolvers import URLPattern
from file.models import PublicFile


@admin.register(PublicFile)
class PublicFileAdmin(BaseAbstractModelAdminMixin, admin.ModelAdmin):
    fields = ["file", "mimetype", "hash", "size"]
    readonly_fields = ["mimetype", "hash", "size"]

    def get_readonly_fields(self, request: HttpRequest, obj: PublicFile | None = None) -> set[str]:
        return super().get_readonly_fields(request, obj) + (["file"] if obj else [])

    def get_urls(self) -> list[URLPattern]:
        return [
            re_path(route=r"^list/$", view=self.admin_site.admin_view(self.list_public_files)),
        ] + super().get_urls()

    def list_public_files(self, request: HttpRequest) -> JsonResponse | HttpResponseNotAllowed:
        if request.method == "GET":
            data = list(PublicFile.objects.filter_active().values(*self.fields))
            return JsonResponse(data=data, safe=False, json_dumps_params={"ensure_ascii": False})
        return HttpResponseNotAllowed(permitted_methods=["GET"])
