from django.contrib import admin
from oauth2_provider.models import get_application_model

from .models import ApplicationSettings, AuditLog


class ApplicationSettingsInline(admin.StackedInline):
    model = ApplicationSettings
    max_num = 1
    can_delete = False


Application = get_application_model()
_base_admin = type(admin.site._registry[Application])
admin.site.unregister(Application)


@admin.register(Application)
class BridgeApplicationAdmin(_base_admin):
    inlines = [*_base_admin.inlines, ApplicationSettingsInline]


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'event', 'success', 'email', 'instance_slug', 'client_id', 'status_code', 'ip')
    list_filter = ('event', 'success', 'instance_slug')
    search_fields = ('email', 'ip', 'client_id', 'message')
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
