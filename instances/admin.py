from django.contrib import admin
from django.utils.html import format_html
from .models import FoxconsInstance

@admin.register(FoxconsInstance)
class FoxconsInstanceAdmin(admin.ModelAdmin):
    list_display = ['icon_preview', 'name', 'theme_preview', 'slug', 'base_url', 'is_active', 'display_order']
    list_filter = ['is_active']
    search_fields = ['name', 'slug', 'base_url']
    ordering = ['display_order', 'name']

    @admin.display(description='Icon')
    def icon_preview(self, obj):
        if obj.icon:
            return format_html(
                '<img src="{}" style="width:40px;height:40px;object-fit:cover;border-radius:6px;">',
                obj.icon.url,
            )
        return '—'

    @admin.display(description='Theme')
    def theme_preview(self, obj):
        return format_html(
            '<span style="display:inline-flex;align-items:center;gap:6px;">'
            '<span style="width:14px;height:14px;border-radius:999px;background:{};border:1px solid #ddd;"></span>'
            '<span style="width:14px;height:14px;border-radius:999px;background:{};border:1px solid #ddd;"></span>'
            '<span style="width:14px;height:14px;border-radius:999px;background:{};border:1px solid #ddd;"></span>'
            '</span>',
            obj.theme_primary,
            obj.theme_secondary,
            obj.theme_text,
        )
