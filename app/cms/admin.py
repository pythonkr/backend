from cms.admin_mixins import RelatedReadonlyFieldsMixin
from cms.models import Page, Section, Sitemap
from django.contrib import admin


class SitemapAdmin(RelatedReadonlyFieldsMixin, admin.ModelAdmin):
    fields = ["id", "parent_sitemap", "page", "name", "order", "display_start_at", "display_end_at"]
    readonly_fields = ["id"]
    related_readonly_config = {
        "page": ["id", "is_active", "css", "title", "subtitle"],
        "parent_sitemap": ["id", "name", "order", "display_start_at", "display_end_at"],
    }

    def get_fieldsets(self, request, obj=...):
        original_fieldsets = super().get_fieldsets(request, obj)
        if obj and obj.parent_sitemap:
            original_fieldsets.append(
                (
                    "Parent Sitemap 정보",
                    {
                        "fields": [f"get_parent_sitemap_{f}" for f in self.related_readonly_config["parent_sitemap"]],
                        "classes": ("collapse",),
                    },
                )
            )
        if obj and obj.page:
            original_fieldsets.append(
                (
                    "Page 정보",
                    {
                        "fields": [f"get_page_{f}" for f in self.related_readonly_config["page"]],
                        "classes": ("collapse",),
                    },
                )
            )
        return original_fieldsets

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("page").select_related("parent_sitemap")


class PageAdmin(admin.ModelAdmin):
    pass


class SectionAdmin(RelatedReadonlyFieldsMixin, admin.ModelAdmin):
    fields = ["id", "page", "order", "css", "body"]
    readonly_fields = ["id"]
    related_readonly_config = {"page": ["id", "is_active", "css", "title", "subtitle"]}

    def get_fieldsets(self, request, obj=...):
        original_fieldsets = super().get_fieldsets(request, obj)
        if obj and obj.page:
            original_fieldsets.append(
                (
                    "Page 정보",
                    {
                        "fields": [f"get_page_{f}" for f in self.related_readonly_config["page"]],
                        "classes": ("collapse",),
                    },
                )
            )
        return original_fieldsets

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("page")


admin.site.register(Sitemap, SitemapAdmin)
admin.site.register(Page, PageAdmin)
admin.site.register(Section, SectionAdmin)
