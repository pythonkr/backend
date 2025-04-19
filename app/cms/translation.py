from cms.models import Page, Section, Sitemap
from modeltranslation.translator import TranslationOptions, register


@register(Page)
class PageTranslationOptions(TranslationOptions):
    fields = ("title", "subtitle")


@register(Sitemap)
class SitemapTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(Section)
class SectionTranslationOptions(TranslationOptions):
    fields = ("body",)
