from cms.models import Page, Section, Sitemap
from django.contrib import admin


class SitemapAdmin(admin.ModelAdmin):
    pass


class PageAdmin(admin.ModelAdmin):
    pass


class SectionAdmin(admin.ModelAdmin):
    pass


admin.site.register(Sitemap, SitemapAdmin)
admin.site.register(Page, PageAdmin)
admin.site.register(Section, SectionAdmin)
