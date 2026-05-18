from django.contrib import admin
from .models import RestoreMetadata, Prompt, Template, AnonymizationRule


@admin.register(RestoreMetadata)
class RestoreMetadataAdmin(admin.ModelAdmin):
    list_display = ('source_id', 'template_type', 'created_at')
    search_fields = ('source_id', 'template_type')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Prompt)
class PromptAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')


@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'template_type', 'updated_at')


@admin.register(AnonymizationRule)
class AnonymizationRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'updated_at')
