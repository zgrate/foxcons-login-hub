from django.contrib import admin
from oauth2_provider.models import get_application_model

from .models import ApplicationSettings


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
