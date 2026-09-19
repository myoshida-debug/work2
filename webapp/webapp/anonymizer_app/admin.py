from django.contrib import admin
from .models import (
    AnonymizationRule,
    OperationLog,
    Patient,
    PatientLinkedPerson,
    Prompt,
    RestoredResult,
    RestoreMetadata,
    Staff,
    Template,
    TemplateInputField,
)


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
    list_display = ('patient_id', 'surname', 'given_name', 'kana_surname', 'kana_given_name', 'sex', 'birth_date', 'primary_diagnosis', 'is_admin_only', 'updated_at')
    search_fields = ('patient_id', 'surname', 'given_name', 'kana_surname', 'kana_given_name', 'primary_diagnosis')
    list_filter = ('sex', 'is_admin_only')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = ('staff_id', 'surname', 'given_name', 'kana_surname', 'kana_given_name', 'occupation_label', 'position_label', 'is_active', 'updated_at')
    search_fields = ('staff_id', 'surname', 'given_name', 'kana_surname', 'kana_given_name', 'occupation_label', 'position_label', 'role_label')
    list_filter = ('is_active',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(PatientLinkedPerson)
class PatientLinkedPersonAdmin(admin.ModelAdmin):
    list_display = ('linked_person_code', 'patient_id', 'branch_no', 'relation_kind', 'surname', 'given_name', 'kana_surname', 'kana_given_name', 'relationship_label', 'is_active', 'updated_at')
    search_fields = ('linked_person_code', 'patient_id', 'surname', 'given_name', 'kana_surname', 'kana_given_name', 'relation_kind', 'relationship_label')
    list_filter = ('relation_kind', 'is_active')
    readonly_fields = ('linked_person_code', 'created_at', 'updated_at')


@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    list_display = ('sort_order', 'is_active', 'name', 'template_type', 'source_filename', 'created_by', 'updated_at')
    list_filter = ('is_active', 'template_type')
    ordering = ('sort_order', 'template_type', 'name', 'id')
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
