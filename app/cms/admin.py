from cms.admin_mixins import RelatedReadonlyFieldsMixin
from cms.models import Page, Section, Sitemap
from core.admin import BaseAbstractModelAdminMixin
from django import forms
from django.contrib import admin
from django.utils.html import format_html

_CODE_PREVIEW_TEMPLATE = """
<style>
  /* ── 래퍼 기본 ── */
  .code-preview-wrapper {{
    display: flex;
    flex-direction: column;
    width: 800px;
    gap: 8px;
    background: #fff;
  }}
  .code-preview-wrapper > textarea {{ display: none !important; }}

  /* ── 툴바 ── */
  .cp-toolbar {{
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px;
    background: #333;
    border-bottom: 1px solid #444;
    position: relative;
    z-index: 2001; /* admin nav 위 */
  }}
  .cp-toolbar button {{
    padding: 4px 8px;
    font-size: 13px;
    border: 1px solid #555;
    background: #444;
    color: #fff;
    cursor: pointer;
  }}
  .cp-toolbar .preview-toggle {{ display: inline-block; }}
  .cp-toolbar .lang-toggle,
  .cp-toolbar .theme-toggle {{ display: none !important; }}
  .code-preview-wrapper.fullscreen .cp-toolbar .lang-toggle,
  .code-preview-wrapper.fullscreen .cp-toolbar .theme-toggle {{
    display: inline-block !important;
  }}
  .lang-toggle.js-mode.active {{ background: #f1c40f; border-color: #d4ac0d; color: #333; }}
  .lang-toggle.ts-mode.active {{ background: #3498db; border-color: #2e86c1; color: #fff; }}
  .theme-toggle.active {{ background: #888; border-color: #666; color: #fff; }}

  /* ── 에디터·프리뷰 컨테이너 ── */
  .cp-main {{
    display: flex;
    flex-direction: column;
    gap: 8px;
    min-height: 0;
  }}
  .code-preview-wrapper:not(.fullscreen) .cp-main {{
    display: none !important;
  }}

  /* 에디터 블록 */
  .editor-block {{
    flex: 1;
    min-height: 0;
    position: relative;
  }}
  .editor-block .CodeMirror,
  .editor-block .CodeMirror-scroll {{
    height: 100% !important;
    overflow: auto !important;
  }}

  /* 프리뷰 iframe */
  .cp-main iframe {{
    flex: 1;
    min-height: 0;
    overflow: auto;
  }}

  /* ── 풀스크린 모드 ── */
  .code-preview-wrapper.fullscreen {{
    position: fixed !important;
    top: 0 !important; left: 0 !important; right: 0 !important; bottom: 0 !important;
    width: 100vw !important;
    height: 100vh !important;
    margin: 0; padding: 0;
    display: flex;
    flex-direction: column;
    background: #fff;
    z-index: 2000;
  }}
  .code-preview-wrapper.fullscreen .cp-main {{
    flex: 1;
    display: flex;
    flex-direction: row;
    min-height: 0;
  }}
  .code-preview-wrapper.fullscreen .editor-block {{
    max-height: none !important;
  }}
  .code-preview-wrapper.fullscreen .cp-toolbar {{
    flex-shrink: 0;
  }}

  /* ── 다크모드 ── */
  .dark-editor .CodeMirror {{ background: #2d2d2d !important; color: #ccc; }}
  .dark-preview iframe {{ background: #2d2d2d; }}
</style>

<div class="code-preview-wrapper" id="cpw_{name}">
  <div class="cp-toolbar">
    <button type="button" class="preview-toggle">Preview Mode</button>
    <button type="button" class="lang-toggle js-mode active" data-lang="js">JS</button>
    <button type="button" class="lang-toggle ts-mode"      data-lang="ts">TS</button>
    <button type="button" class="theme-toggle" data-target="editor">Editor Dark</button>
    <button type="button" class="theme-toggle" data-target="preview">Preview Dark</button>
  </div>
  {ta}
  <div class="cp-main">
    <div class="editor-block" id="editor_{name}"></div>
    <iframe id="preview_{name}"></iframe>
  </div>
</div>
"""


class CodeEditorWidget(forms.Textarea):
    class Media:
        css = {
            "all": (
                "https://unpkg.com/codemirror@5.65.5/lib/codemirror.css",
                "https://unpkg.com/codemirror@5.65.5/theme/dracula.css",
            )
        }
        js = (
            "https://unpkg.com/codemirror@5.65.5/lib/codemirror.js",
            "https://unpkg.com/codemirror@5.65.5/mode/javascript/javascript.js",
            "https://unpkg.com/@babel/standalone/babel.min.js",
            "admin/js/editor.js",
        )

    def render(self, name, value, attrs=None, renderer=None):
        ta = super().render(name, value, attrs, renderer)
        return format_html(_CODE_PREVIEW_TEMPLATE, name=name, ta=ta)


class SectionAdminForm(forms.ModelForm):
    class Meta:
        model = Section
        fields = "__all__"
        widgets = {"body": CodeEditorWidget()}


@admin.register(Sitemap)
class SitemapAdmin(BaseAbstractModelAdminMixin, RelatedReadonlyFieldsMixin, admin.ModelAdmin):
    fields = [
        "id",
        "parent_sitemap",
        "route_code",
        "route",
        "page",
        "name",
        "order",
        "display_start_at",
        "display_end_at",
    ]
    readonly_fields = ["id", "route"]
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
        return super().get_queryset(request).select_related("page", "parent_sitemap")


@admin.register(Page)
class PageAdmin(BaseAbstractModelAdminMixin, admin.ModelAdmin):
    fields = ["id", "css", "title", "subtitle"]
    readonly_fields = ["id"]
    queryset = Page.objects.prefetch_related("sections")


@admin.register(Section)
class SectionAdmin(BaseAbstractModelAdminMixin, RelatedReadonlyFieldsMixin, admin.ModelAdmin):
    form = SectionAdminForm
    queryset = Section.objects.select_related("page")
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
