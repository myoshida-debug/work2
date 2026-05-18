from django.contrib import admin
from .models import RestoreMetadata


@admin.register(RestoreMetadata)
class RestoreMetadataAdmin(admin.ModelAdmin):
    list_display = ('source_id', 'template_type', 'created_at')
    search_fields = ('source_id', 'template_type')
    readonly_fields = ('created_at', 'updated_at')
