from modeltranslation.translator import register, TranslationOptions
from cms.page.models import Page, Sitemap, Section

@register(Page)
class PageTranslationOptions(TranslationOptions):
    fields = ('title', 'subtitle')

@register(Sitemap)
class SitemapTranslationOptions(TranslationOptions):
    fields = ('name',)

@register(Section)
class SectionTranslationOptions(TranslationOptions):
    fields = ('body',)
