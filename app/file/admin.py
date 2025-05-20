from django.contrib import admin
from django.http.request import HttpRequest
from django.http.response import HttpResponseNotAllowed, JsonResponse
from django.urls import re_path
from django.urls.resolvers import URLPattern
from file.models import PublicFile


@admin.register(PublicFile)
class PublicFileAdmin(admin.ModelAdmin):
    fields = ["id", "file", "alternate_text", "created_at", "updated_at", "deleted_at"]
    readonly_fields = ["id", "created_at", "updated_at", "deleted_at"]

    def get_urls(self) -> list[URLPattern]:
        return [
            re_path(route=r"^list/$", view=self.admin_site.admin_view(self.list_public_files)),
        ] + super().get_urls()

    def list_public_files(self, request: HttpRequest) -> JsonResponse | HttpResponseNotAllowed:
        if request.method == "GET":
            return JsonResponse(data=PublicFile.objects.values(self.fields))
        return HttpResponseNotAllowed(permitted_methods=["GET"])
