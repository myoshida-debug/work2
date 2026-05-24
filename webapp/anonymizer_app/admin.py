from django.contrib import admin
from .models import AnonymizationRule, OperationLog, Patient, Prompt, RestoredResult, RestoreMetadata, Template, TemplateInputField


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


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ('patient_id', 'surname', 'given_name', 'kana_surname', 'kana_given_name', 'sex', 'birth_date', 'primary_diagnosis', 'updated_at')
    search_fields = ('patient_id', 'surname', 'given_name', 'kana_surname', 'kana_given_name', 'primary_diagnosis')
    list_filter = ('sex',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'template_type', 'source_filename', 'created_by', 'updated_at')
    readonly_fields = ('source_filename',)


@admin.register(TemplateInputField)
class TemplateInputFieldAdmin(admin.ModelAdmin):
    list_display = ('template_type', 'field_key', 'label', 'input_type', 'textarea_rows', 'sort_order', 'is_active', 'updated_at')
    search_fields = ('template_type', 'field_key', 'label')
    list_filter = ('template_type', 'input_type', 'is_active')


@admin.register(AnonymizationRule)
class AnonymizationRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'updated_at')


@admin.register(OperationLog)
class OperationLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'actor_username', 'action', 'target_type', 'target_id', 'source_ip', 'import_source_ip', 'result')
    search_fields = ('actor_username', 'action', 'target_type', 'target_id', 'source_ip', 'import_source_ip', 'error_message')
    list_filter = ('result', 'action')
    readonly_fields = ('created_at',)
