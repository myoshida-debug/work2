from django.contrib import admin
from .models import AnonymizationRule, OperationLog, Prompt, RestoredResult, RestoreMetadata, Template


@admin.register(RestoreMetadata)
class RestoreMetadataAdmin(admin.ModelAdmin):
    list_display = ('source_id', 'template_type', 'owner', 'status', 'created_at')
    search_fields = ('source_id', 'template_type', 'owner__username')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Prompt)
class PromptAdmin(admin.ModelAdmin):
    list_display = ('name', 'source_id', 'owner', 'status', 'created_at')
    search_fields = ('name', 'source_id', 'owner__username')


@admin.register(RestoredResult)
class RestoredResultAdmin(admin.ModelAdmin):
    list_display = ('result_id', 'source_id', 'template_type', 'owner', 'reviewer', 'status', 'created_at')
    search_fields = ('result_id', 'source_id', 'template_type', 'reviewer', 'owner__username')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'template_type', 'source_filename', 'created_by', 'updated_at')
    readonly_fields = ('source_filename',)


@admin.register(AnonymizationRule)
class AnonymizationRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'updated_at')


@admin.register(OperationLog)
class OperationLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'actor_username', 'action', 'target_type', 'target_id', 'source_ip', 'import_source_ip', 'result')
    search_fields = ('actor_username', 'action', 'target_type', 'target_id', 'source_ip', 'import_source_ip', 'error_message')
    list_filter = ('result', 'action')
    readonly_fields = ('created_at',)
