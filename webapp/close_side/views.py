import csv
import datetime
import difflib
import json
import re
import uuid
from copy import deepcopy
from io import StringIO
from urllib.parse import urlencode
from pathlib import Path

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Case, IntegerField, Q, Value, When
from django.db.models.functions import Concat
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_http_methods

from anonymizer_app.forms import (
    AnonymizeForm,
    DMZExportForm,
    DMZResultImportForm,
    PatientForm,
    PatientLinkedPersonForm,
    PatientLinkedPersonImportForm,
    PatientLinkedPersonSearchForm,
    PatientImportForm,
    PatientSearchForm,
    StaffForm,
    StaffImportForm,
    StaffSearchForm,
    PromptForm,
    TemplateForm,
    TemplateInputDefaultsForm,
)
from anonymizer_app.history_utils import (
    HISTORY_LIMIT,
    decorate_operation_logs,
    filter_history_items,
    operation_action_label,
)
from anonymizer_app.models import (
    AnonymizationRule,
    FIELD_INPUT_TYPE_CHOICES,
    OperationLog,
    Patient,
    PatientLinkedPerson,
    Prompt,
    RestoredResult,
    RestoreMetadata,
    Staff,
    Template,
    TemplateInputCheckboxGroup,
    TemplateInputCheckboxOption,
    TemplateInputDefault,
    TemplateInputField,
)
from anonymizer_app.modules.anonymize import anonymize_text, build_prompt_payload, restore_text
from anonymizer_app.network_policy import get_client_ip
from anonymizer_app.structured_input import (
    build_anonymized_patient_id,
    build_source_input_data,
    build_source_text_from_structured_input,
    build_source_text_from_source_input_data,
    build_structured_input_labels,
    collect_structured_input,
    normalize_source_input_data,
    normalize_structured_input,
    validate_structured_input,
)
from anonymizer_app.template_input_schemas import (
    TEMPLATE_INPUT_SCHEMA_ALIASES,
    TEMPLATE_INPUT_SCHEMAS,
    get_template_input_schema,
    get_template_input_schema_map,
)
from anonymizer_app.prompt_template_store import (
    delete_template_source,
    get_template_source_by_filename,
    get_template_source_by_name,
    load_basic_template,
    list_template_sources,
    sync_templates_to_db,
    write_template_source,
)
from close_side.transcription import (
    TranscriptionConfigurationError,
    TranscriptionRequestError,
    TranscriptionServiceError,
    transcribe_audio_file,
)


def _is_admin(user) -> bool:
    return bool(user.is_staff or user.is_superuser)


def _owned_queryset(queryset, user):
    if _is_admin(user):
        return queryset
    return queryset.filter(owner=user)


FIELD_INPUT_TYPE_VALUES = {value for value, _label in FIELD_INPUT_TYPE_CHOICES}

PATIENT_SEX_DISPLAY_TO_VALUE = {
    '男': 'male',
    '男性': 'male',
    'm': 'male',
    'male': 'male',
    '女': 'female',
    '女性': 'female',
    'f': 'female',
    'female': 'female',
    'その他': 'other',
    'other': 'other',
    '不明': 'unknown',
    'unknown': 'unknown',
}
PATIENT_SEX_VALUE_TO_DISPLAY = {value: label for value, label in Patient.SEX_CHOICES}
PATIENT_CSV_HEADER_ALIASES = {
    'id': 'patient_id',
    'patient_id': 'patient_id',
    '患者id': 'patient_id',
    '患者_id': 'patient_id',
    '患者id番号': 'patient_id',
    '姓': 'surname',
    '名': 'given_name',
    'ふりかな姓': 'kana_surname',
    'ふりかな名': 'kana_given_name',
    'ふりがな姓': 'kana_surname',
    'ふりがな名': 'kana_given_name',
    'ふりかな': 'kana_full_name',
    'ふりがな': 'kana_full_name',
    '生年月日': 'birth_date',
    '性別': 'sex',
    '主病名': 'primary_diagnosis',
}
STAFF_CSV_HEADER_ALIASES = {
    'id': 'staff_id',
    'staff_id': 'staff_id',
    '職員id': 'staff_id',
    '職員_id': 'staff_id',
    '職員id番号': 'staff_id',
    '姓': 'surname',
    '名': 'given_name',
    'ふりかな姓': 'kana_surname',
    'ふりかな名': 'kana_given_name',
    'ふりがな姓': 'kana_surname',
    'ふりがな名': 'kana_given_name',
    'ふりかな': 'kana_full_name',
    'ふりがな': 'kana_full_name',
    '職種': 'occupation_label',
    '役割': 'position_label',
    '職種ラベル': 'occupation_label',
    '役割ラベル': 'position_label',
    '役職': 'position_label',
    '職位': 'position_label',
    'ラベル': 'occupation_label',
    '有効': 'is_active',
    '稼働': 'is_active',
    'active': 'is_active',
    'is_active': 'is_active',
}
LINKED_PERSON_CSV_HEADER_ALIASES = {
    'id': 'branch_no',
    'family_id': 'branch_no',
    'guardian_id': 'branch_no',
    '家族id': 'branch_no',
    '家族_id': 'branch_no',
    '後見人id': 'branch_no',
    '後見人_id': 'branch_no',
    '患者id': 'patient_id',
    'patient_id': 'patient_id',
    '患者_id': 'patient_id',
    '枝番': 'branch_no',
    '枝番番号': 'branch_no',
    '番号': 'branch_no',
    '姓': 'surname',
    '名': 'given_name',
    'ふりかな姓': 'kana_surname',
    'ふりかな名': 'kana_given_name',
    'ふりがな姓': 'kana_surname',
    'ふりがな名': 'kana_given_name',
    'ふりかな': 'kana_full_name',
    'ふりがな': 'kana_full_name',
    '種別': 'relation_kind',
    '分類': 'relation_kind',
    '区分種別': 'relation_kind',
    '属性種別': 'relation_kind',
    '属性': 'relationship_label',
    '続柄': 'relationship_label',
    '区分': 'relationship_label',
    '関係': 'relationship_label',
    '有効': 'is_active',
    '稼働': 'is_active',
    'active': 'is_active',
    'is_active': 'is_active',
}
FAMILY_CSV_HEADER_ALIASES = LINKED_PERSON_CSV_HEADER_ALIASES
GUARDIAN_CSV_HEADER_ALIASES = LINKED_PERSON_CSV_HEADER_ALIASES


def _template_supports_patient_master(template_type: str) -> bool:
    return str(template_type or '').strip() != '委員会議事録'


def _patient_full_name(patient: Patient | None) -> str:
    if patient is None:
        return ''
    return f'{patient.surname}{patient.given_name}'.strip()


def _patient_kana_full_name(patient: Patient | None) -> str:
    if patient is None:
        return ''
    return f'{patient.kana_surname}{patient.kana_given_name}'.strip()


def _patient_name_variants(patient: Patient | None) -> list[str]:
    if patient is None:
        return []
    return patient.name_variants()


def _staff_full_name(staff: Staff | None) -> str:
    if staff is None:
        return ''
    return f'{staff.surname}{staff.given_name}'.strip()


def _staff_kana_full_name(staff: Staff | None) -> str:
    if staff is None:
        return ''
    return f'{staff.kana_surname}{staff.kana_given_name}'.strip()


def _staff_name_variants(staff: Staff | None) -> list[str]:
    if staff is None:
        return []
    return staff.name_variants()


def _staff_anonymization_label_prefix(staff: Staff | None) -> str:
    if staff is None:
        return '職員'
    return staff.anonymization_label_prefix or '職員'


def _family_full_name(family: PatientLinkedPerson | None) -> str:
    if family is None:
        return ''
    return f'{family.surname}{family.given_name}'.strip()


def _family_kana_full_name(family: PatientLinkedPerson | None) -> str:
    if family is None:
        return ''
    return f'{family.kana_surname}{family.kana_given_name}'.strip()


def _family_name_variants(family: PatientLinkedPerson | None) -> list[str]:
    if family is None:
        return []
    return family.name_variants()


def _family_anonymization_label_prefix(family: PatientLinkedPerson | None) -> str:
    if family is None:
        return '家族'
    return family.anonymization_label_prefix or '家族'


def _guardian_full_name(guardian: PatientLinkedPerson | None) -> str:
    if guardian is None:
        return ''
    return f'{guardian.surname}{guardian.given_name}'.strip()


def _guardian_kana_full_name(guardian: PatientLinkedPerson | None) -> str:
    if guardian is None:
        return ''
    return f'{guardian.kana_surname}{guardian.kana_given_name}'.strip()


def _guardian_name_variants(guardian: PatientLinkedPerson | None) -> list[str]:
    if guardian is None:
        return []
    return guardian.name_variants()


def _guardian_anonymization_label_prefix(guardian: PatientLinkedPerson | None) -> str:
    if guardian is None:
        return '後見人'
    return guardian.anonymization_label_prefix or '後見人'


def _patient_payload(patient: Patient | None) -> dict[str, object]:
    if patient is None:
        return {}
    return {
        'patient_id': patient.patient_id or '',
        'anonymized_patient_id': build_anonymized_patient_id(patient.patient_id),
        'surname': patient.surname or '',
        'given_name': patient.given_name or '',
        'kana_surname': patient.kana_surname or '',
        'kana_given_name': patient.kana_given_name or '',
        'full_name': _patient_full_name(patient),
        'kana_full_name': _patient_kana_full_name(patient),
        'birth_date': patient.birth_date.isoformat() if patient.birth_date else '',
        'birth_date_display': patient.birth_date.strftime('%Y-%m-%d') if patient.birth_date else '',
        'sex': patient.sex or '',
        'sex_display': patient.get_sex_display() if patient.sex else '',
        'primary_diagnosis': patient.primary_diagnosis or '',
    }


def _staff_payload(staff: Staff | None) -> dict[str, object]:
    if staff is None:
        return {}
    return {
        'staff_id': staff.staff_id or '',
        'surname': staff.surname or '',
        'given_name': staff.given_name or '',
        'kana_surname': staff.kana_surname or '',
        'kana_given_name': staff.kana_given_name or '',
        'full_name': _staff_full_name(staff),
        'kana_full_name': _staff_kana_full_name(staff),
        'role_label': staff.role_label or '',
        'occupation_label': staff.occupation_label or '',
        'position_label': staff.position_label or '',
        'display_role_label': staff.display_role_label,
        'anonymization_label_prefix': _staff_anonymization_label_prefix(staff),
        'is_active': bool(staff.is_active),
    }


def _family_payload(family: PatientLinkedPerson | None) -> dict[str, object]:
    if family is None:
        return {}
    return {
        'linked_person_code': family.linked_person_code or '',
        'linked_person_display_label': family.linked_person_display_label,
        'branch_no': family.branch_no,
        'branch_display_label': family.branch_display_label,
        'patient_id': family.patient_id or '',
        'relation_kind': family.relation_kind or '',
        'relation_kind_label': family.relation_kind_label,
        'surname': family.surname or '',
        'given_name': family.given_name or '',
        'kana_surname': family.kana_surname or '',
        'kana_given_name': family.kana_given_name or '',
        'full_name': _family_full_name(family),
        'kana_full_name': _family_kana_full_name(family),
        'relationship_label': family.relationship_label or '',
        'display_relationship_label': family.relationship_display_label,
        'anonymization_label_prefix': _family_anonymization_label_prefix(family),
        'is_active': bool(family.is_active),
    }


def _guardian_payload(guardian: PatientLinkedPerson | None) -> dict[str, object]:
    if guardian is None:
        return {}
    return {
        'linked_person_code': guardian.linked_person_code or '',
        'linked_person_display_label': guardian.linked_person_display_label,
        'branch_no': guardian.branch_no,
        'branch_display_label': guardian.branch_display_label,
        'patient_id': guardian.patient_id or '',
        'relation_kind': guardian.relation_kind or '',
        'relation_kind_label': guardian.relation_kind_label,
        'surname': guardian.surname or '',
        'given_name': guardian.given_name or '',
        'kana_surname': guardian.kana_surname or '',
        'kana_given_name': guardian.kana_given_name or '',
        'full_name': _guardian_full_name(guardian),
        'kana_full_name': _guardian_kana_full_name(guardian),
        'relationship_label': guardian.relationship_label or '',
        'display_relationship_label': guardian.relationship_display_label,
        'anonymization_label_prefix': _guardian_anonymization_label_prefix(guardian),
        'is_active': bool(guardian.is_active),
    }


def _patient_restore_map(patient_profile: dict[str, object] | None) -> dict[str, str]:
    if not isinstance(patient_profile, dict):
        return {}

    anonymized_patient_id = str(patient_profile.get('anonymized_patient_id') or '').strip()
    patient_id = str(patient_profile.get('patient_id') or '').strip()
    if anonymized_patient_id and patient_id:
        return {anonymized_patient_id: patient_id}
    return {}


def _augment_restore_map_with_patient_info(
    restore_map: dict[str, str] | None,
    patient_profile: dict[str, object] | None,
) -> dict[str, str]:
    merged = dict(restore_map or {})
    for label, original in _patient_restore_map(patient_profile).items():
        merged.setdefault(label, original)
    return merged


def _patient_profile_for_source_id(source_id: str, user) -> dict[str, object]:
    source_id = str(source_id or '').strip()
    if not source_id:
        return {}

    prompt = _owned_queryset(Prompt.objects.all(), user).filter(source_id=source_id).order_by('-updated_at').first()
    if prompt is None:
        return {}

    source_input_data = normalize_source_input_data(prompt.source_input_data)
    patient_profile = source_input_data.get('patient') or {}
    if not isinstance(patient_profile, dict):
        return {}
    return patient_profile


def _patient_id_value(patient_record: Patient | None) -> str:
    if patient_record is None:
        return ''
    return str(patient_record.patient_id or '').strip()


def _family_queryset_for_patient_id(patient_id: str):
    patient_id = str(patient_id or '').strip()
    if not patient_id:
        return PatientLinkedPerson.objects.none()
    return PatientLinkedPerson.objects.filter(patient_id=patient_id, relation_kind='family')


def _guardian_queryset_for_patient_id(patient_id: str):
    patient_id = str(patient_id or '').strip()
    if not patient_id:
        return PatientLinkedPerson.objects.none()
    return PatientLinkedPerson.objects.filter(patient_id=patient_id, relation_kind='guardian')


def _staff_for_staff_id(staff_id: str) -> Staff | None:
    staff_id = str(staff_id or '').strip()
    if not staff_id:
        return None
    return Staff.objects.filter(staff_id=staff_id).first()


def _alphabet_label(index: int) -> str:
    index += 1
    letters = []
    while index:
        index, remainder = divmod(index - 1, 26)
        letters.append(chr(ord('A') + remainder))
    return ''.join(reversed(letters))


def _append_labelled_name_groups(
    groups: list[dict[str, object]],
    queryset,
    *,
    name_getter,
    prefix_getter,
    original_getter,
    sort_fields: tuple[str, ...],
) -> None:
    counters: dict[str, int] = {}
    ordered_queryset = queryset.order_by(*sort_fields)
    for item in ordered_queryset:
        names = name_getter(item)
        if not names:
            continue
        prefix = str(prefix_getter(item) or '').strip() or '関連者'
        counter = counters.get(prefix, 0)
        counters[prefix] = counter + 1
        groups.append({
            'label': f'{prefix}{_alphabet_label(counter)}',
            'names': names,
            'original': original_getter(item),
        })


def _preferred_entity_groups_for_anonymization(patient_record: Patient | None = None) -> list[dict[str, object]]:
    groups: list[dict[str, object]] = []

    if patient_record is not None:
        patient_names = _patient_name_variants(patient_record)
        if patient_names:
            groups.append({
                'label': '患者本人A',
                'names': patient_names,
                'original': _patient_full_name(patient_record),
            })

    _append_labelled_name_groups(
        groups,
        Staff.objects.filter(is_active=True),
        name_getter=_staff_name_variants,
        prefix_getter=_staff_anonymization_label_prefix,
        original_getter=_staff_full_name,
        sort_fields=('occupation_label', 'position_label', 'kana_surname', 'kana_given_name', 'staff_id'),
    )

    patient_id = _patient_id_value(patient_record)
    if patient_id:
        _append_labelled_name_groups(
            groups,
            PatientLinkedPerson.objects.filter(patient_id=patient_id, is_active=True),
            name_getter=_family_name_variants,
            prefix_getter=_family_anonymization_label_prefix,
            original_getter=_family_full_name,
            sort_fields=('branch_no', 'relation_kind', 'kana_surname', 'kana_given_name', 'patient_id'),
        )

    return groups


def _patient_display_label(patient_profile: dict[str, object] | None) -> str:
    if not isinstance(patient_profile, dict):
        return ''

    patient_id = str(patient_profile.get('patient_id') or patient_profile.get('anonymized_patient_id') or '').strip()
    full_name = str(patient_profile.get('full_name') or '').strip()
    if patient_id and full_name:
        return f'{patient_id} {full_name}'
    return patient_id or full_name


def _patient_basic_info_block(template_type: str, patient_profile: dict[str, object] | None) -> str:
    if not _template_supports_patient_master(template_type):
        return ''
    if not isinstance(patient_profile, dict):
        return ''

    patient_id = str(patient_profile.get('patient_id') or '').strip()
    full_name = str(patient_profile.get('full_name') or '').strip()
    sex = str(
        patient_profile.get('sex_display')
        or PATIENT_SEX_VALUE_TO_DISPLAY.get(str(patient_profile.get('sex') or '').strip().lower())
        or patient_profile.get('sex')
        or ''
    ).strip()
    birth_date = str(patient_profile.get('birth_date_display') or patient_profile.get('birth_date') or '').strip()
    primary_diagnosis = str(patient_profile.get('primary_diagnosis') or '').strip()

    lines: list[str] = []
    if patient_id:
        lines.append(f'・ID: {patient_id}')
    if full_name:
        lines.append(f'・氏名: {full_name}')
    if sex:
        lines.append(f'・性別: {sex}')
    if birth_date:
        lines.append(f'・生年月日: {birth_date}')
    if primary_diagnosis:
        lines.append(f'・主病名: {primary_diagnosis}')

    if not lines:
        return ''
    return '【患者基本情報】\n' + '\n'.join(lines)


def _prepend_patient_basic_info_to_restored_text(
    restored_text: str,
    template_type: str,
    patient_profile: dict[str, object] | None,
) -> str:
    body = str(restored_text or '').strip()
    block = _patient_basic_info_block(template_type, patient_profile)
    if not block:
        return body
    if body.startswith('【患者基本情報】'):
        return body
    if not body:
        return block
    return f'{block}\n\n{body}'


def _prepend_blank_lines_for_patient_basic_info(
    result_text: str,
    template_type: str,
    patient_profile: dict[str, object] | None,
) -> str:
    body = str(result_text or '').strip()
    if not body:
        return body
    if not _patient_basic_info_block(template_type, patient_profile):
        return body
    return ('\n' * 7) + body


def _patient_for_patient_id(patient_id: str) -> Patient | None:
    patient_id = str(patient_id or '').strip()
    if not patient_id:
        return None
    return Patient.objects.filter(patient_id=patient_id).first()


def _normalize_patient_sex(value: object) -> str:
    key = str(value or '').strip()
    if not key:
        return ''
    normalized = PATIENT_SEX_DISPLAY_TO_VALUE.get(key) or PATIENT_SEX_DISPLAY_TO_VALUE.get(key.lower())
    if normalized:
        return normalized
    return ''


def _parse_patient_birth_date(value: object):
    text = str(value or '').strip()
    if not text:
        return None
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%Y年%m月%d日'):
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except Exception:
            continue
    try:
        return datetime.date.fromisoformat(text)
    except Exception:
        return None


def _split_name_value(value: object) -> tuple[str, str]:
    text = str(value or '').strip()
    if not text:
        return '', ''
    parts = re.split(r'[\s　]+', text, maxsplit=1)
    if len(parts) == 1:
        return parts[0], ''
    return parts[0], parts[1]


def _normalize_patient_csv_row(raw_row: dict[str, str]) -> dict[str, object]:
    normalized: dict[str, object] = {
        'patient_id': '',
        'surname': '',
        'given_name': '',
        'kana_surname': '',
        'kana_given_name': '',
        'birth_date': None,
        'sex': '',
        'primary_diagnosis': '',
    }
    for raw_key, raw_value in raw_row.items():
        key = PATIENT_CSV_HEADER_ALIASES.get(str(raw_key or '').strip().lower())
        if not key:
            # 日本語ヘッダーのまま来ることが多いので原文でも再確認する
            key = PATIENT_CSV_HEADER_ALIASES.get(str(raw_key or '').strip())
        value = str(raw_value or '').strip()
        if not key or not value:
            continue
        if key == 'kana_full_name':
            kana_surname, kana_given_name = _split_name_value(value)
            if kana_surname and not normalized['kana_surname']:
                normalized['kana_surname'] = kana_surname
            if kana_given_name and not normalized['kana_given_name']:
                normalized['kana_given_name'] = kana_given_name
            continue
        if key == 'birth_date':
            normalized['birth_date'] = _parse_patient_birth_date(value)
            continue
        if key == 'sex':
            normalized['sex'] = _normalize_patient_sex(value)
            continue
        normalized[key] = value
    return normalized


def _decode_patient_csv_file(uploaded_file) -> str:
    raw_bytes = uploaded_file.read()
    if hasattr(uploaded_file, 'seek'):
        uploaded_file.seek(0)
    for encoding in ('utf-8-sig', 'cp932', 'utf-8'):
        try:
            return raw_bytes.decode(encoding)
        except Exception:
            continue
    return raw_bytes.decode('utf-8', errors='ignore')


def _patient_sort_queryset(queryset, sort_key: str):
    sort_key = str(sort_key or 'patient_id').strip() or 'patient_id'
    if sort_key == 'kana':
        return queryset.order_by('kana_surname', 'kana_given_name', 'patient_id')
    if sort_key == 'sex':
        sex_order = Case(
            When(sex='male', then=Value(0)),
            When(sex='female', then=Value(1)),
            When(sex='other', then=Value(2)),
            When(sex='unknown', then=Value(3)),
            default=Value(4),
            output_field=IntegerField(),
        )
        return queryset.annotate(_sex_order=sex_order).order_by('_sex_order', 'patient_id')
    if sort_key == 'birth_date':
        birth_date_order = Case(
            When(birth_date__isnull=True, then=Value(1)),
            default=Value(0),
            output_field=IntegerField(),
        )
        return queryset.annotate(_birth_date_order=birth_date_order).order_by('_birth_date_order', 'birth_date', 'patient_id')
    return queryset.order_by('patient_id')


def _patient_upsert_from_csv_row(normalized_row: dict[str, object]) -> tuple[Patient | None, bool, bool]:
    patient_id = str(normalized_row.get('patient_id') or '').strip()
    if not patient_id:
        return None, False, False

    defaults: dict[str, object] = {}
    for field_name in ('surname', 'given_name', 'kana_surname', 'kana_given_name', 'primary_diagnosis', 'sex'):
        value = str(normalized_row.get(field_name) or '').strip()
        if value:
            defaults[field_name] = value
    birth_date = normalized_row.get('birth_date')
    if birth_date:
        defaults['birth_date'] = birth_date

    patient, created = Patient.objects.get_or_create(patient_id=patient_id, defaults=defaults)
    if created:
        return patient, True, bool(defaults)

    changed_fields: list[str] = []
    for field_name, value in defaults.items():
        if getattr(patient, field_name) != value:
            setattr(patient, field_name, value)
            changed_fields.append(field_name)
    if changed_fields:
        patient.save(update_fields=changed_fields + ['updated_at'])
    return patient, False, bool(changed_fields)


def _import_patient_csv(uploaded_file) -> dict[str, int]:
    csv_text = _decode_patient_csv_file(uploaded_file)
    reader = csv.DictReader(StringIO(csv_text))
    created_count = 0
    updated_count = 0
    skipped_count = 0
    seen_ids: set[str] = set()

    with transaction.atomic():
        for raw_row in reader:
            normalized_row = _normalize_patient_csv_row(raw_row)
            patient_id = str(normalized_row.get('patient_id') or '').strip()
            if not patient_id:
                skipped_count += 1
                continue

            patient, created, changed = _patient_upsert_from_csv_row(normalized_row)
            if patient is None:
                skipped_count += 1
                continue
            if created:
                created_count += 1
            elif changed:
                updated_count += 1
            else:
                skipped_count += 1
            seen_ids.add(patient_id)

    if not seen_ids:
        raise ValueError(
            '有効な患者IDが見つかりませんでした。'
            'CSVの1行目が `ID,姓,名,ふりかな姓,ふりかな名,生年月日,性別,主病名` になっているか、'
            'Excelファイルをそのまま選んでいないか確認してください。'
        )

    return {
        'created': created_count,
        'updated': updated_count,
        'skipped': skipped_count,
        'processed': created_count + updated_count,
        'unique_ids': len(seen_ids),
    }


def _normalize_staff_is_active(value: object) -> bool | None:
    text = str(value or '').strip()
    if not text:
        return None

    normalized = text.casefold()
    if normalized in {'1', 'true', 'yes', 'on', 't', 'y', '有効', 'はい', '稼働'}:
        return True
    if normalized in {'0', 'false', 'no', 'off', 'f', 'n', '無効', 'いいえ'}:
        return False
    return bool(_is_truthy(value))


def _normalize_staff_csv_row(raw_row: dict[str, str]) -> dict[str, object]:
    normalized: dict[str, object] = {
        'staff_id': '',
        'surname': '',
        'given_name': '',
        'kana_surname': '',
        'kana_given_name': '',
        'occupation_label': '',
        'position_label': '',
        'is_active': None,
    }
    for raw_key, raw_value in raw_row.items():
        key = STAFF_CSV_HEADER_ALIASES.get(str(raw_key or '').strip().lower())
        if not key:
            key = STAFF_CSV_HEADER_ALIASES.get(str(raw_key or '').strip())
        value = str(raw_value or '').strip()
        if not key or not value:
            continue
        if key == 'kana_full_name':
            kana_surname, kana_given_name = _split_name_value(value)
            if kana_surname and not normalized['kana_surname']:
                normalized['kana_surname'] = kana_surname
            if kana_given_name and not normalized['kana_given_name']:
                normalized['kana_given_name'] = kana_given_name
            continue
        if key == 'is_active':
            normalized['is_active'] = _normalize_staff_is_active(value)
            continue
        normalized[key] = value
    return normalized


def _staff_sort_queryset(queryset, sort_key: str):
    sort_key = str(sort_key or 'staff_id').strip() or 'staff_id'
    if sort_key == 'kana':
        return queryset.order_by('kana_surname', 'kana_given_name', 'staff_id')
    if sort_key == 'occupation_label':
        return queryset.order_by('occupation_label', 'staff_id')
    if sort_key == 'position_label':
        return queryset.order_by('position_label', 'staff_id')
    if sort_key == 'is_active':
        active_order = Case(
            When(is_active=True, then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        )
        return queryset.annotate(_active_order=active_order).order_by('_active_order', 'occupation_label', 'position_label', 'staff_id')
    if sort_key == 'updated_at':
        return queryset.order_by('-updated_at', 'staff_id')
    return queryset.order_by('staff_id')


def _staff_upsert_from_csv_row(normalized_row: dict[str, object]) -> tuple[Staff | None, bool, bool]:
    staff_id = str(normalized_row.get('staff_id') or '').strip()
    if not staff_id:
        return None, False, False

    defaults: dict[str, object] = {}
    for field_name in ('surname', 'given_name', 'kana_surname', 'kana_given_name', 'occupation_label', 'position_label'):
        value = str(normalized_row.get(field_name) or '').strip()
        if value:
            defaults[field_name] = value
    is_active = normalized_row.get('is_active')
    if is_active is not None:
        defaults['is_active'] = bool(is_active)

    staff, created = Staff.objects.get_or_create(staff_id=staff_id, defaults=defaults)
    if created:
        return staff, True, bool(defaults)

    changed_fields: list[str] = []
    for field_name, value in defaults.items():
        if getattr(staff, field_name) != value:
            setattr(staff, field_name, value)
            changed_fields.append(field_name)
    if changed_fields:
        staff.save(update_fields=changed_fields + ['updated_at'])
    return staff, False, bool(changed_fields)


def _import_staff_csv(uploaded_file) -> dict[str, int]:
    csv_text = _decode_patient_csv_file(uploaded_file)
    reader = csv.DictReader(StringIO(csv_text))
    created_count = 0
    updated_count = 0
    skipped_count = 0
    seen_ids: set[str] = set()

    with transaction.atomic():
        for raw_row in reader:
            normalized_row = _normalize_staff_csv_row(raw_row)
            staff_id = str(normalized_row.get('staff_id') or '').strip()
            if not staff_id:
                skipped_count += 1
                continue

            staff, created, changed = _staff_upsert_from_csv_row(normalized_row)
            if staff is None:
                skipped_count += 1
                continue
            if created:
                created_count += 1
            elif changed:
                updated_count += 1
            else:
                skipped_count += 1
            seen_ids.add(staff_id)

    if not seen_ids:
        raise ValueError(
            '有効な職員IDが見つかりませんでした。'
            'CSVの1行目が `ID,姓,名,ふりかな姓,ふりかな名,職種,役職,有効` になっているか、'
            'Excelファイルをそのまま選んでいないか確認してください。'
        )

    return {
        'created': created_count,
        'updated': updated_count,
        'skipped': skipped_count,
        'processed': created_count + updated_count,
        'unique_ids': len(seen_ids),
    }


def _normalize_patient_linked_is_active(value: object) -> bool | None:
    text = str(value or '').strip()
    if not text:
        return None

    normalized = text.casefold()
    if normalized in {'1', 'true', 'yes', 'on', 't', 'y', '有効', 'はい', '稼働'}:
        return True
    if normalized in {'0', 'false', 'no', 'off', 'f', 'n', '無効', 'いいえ'}:
        return False
    return bool(_is_truthy(value))


def _normalize_branch_no_value(value: object) -> int | None:
    text = str(value or '').strip()
    if not text:
        return None
    if text.isdigit():
        branch_no = int(text)
        return branch_no if branch_no > 0 else None
    match = re.search(r'(\d+)$', text)
    if not match:
        return None
    branch_no = int(match.group(1))
    return branch_no if branch_no > 0 else None


def _normalize_relation_kind_value(value: object) -> str | None:
    text = str(value or '').strip().casefold()
    if not text:
        return None
    if text in {'family', '家族', 'familly', '親族', 'family_member', 'familymember'}:
        return 'family'
    if text in {'guardian', '後見人', '保佐人', '補助人', '成年後見人', '法定後見人'}:
        return 'guardian'
    if '後見' in text or '保佐' in text or '補助' in text:
        return 'guardian'
    if '家族' in text or '親族' in text:
        return 'family'
    return None


def _normalize_linked_person_csv_row(raw_row: dict[str, str], header_aliases: dict[str, str]) -> dict[str, object]:
    normalized: dict[str, object] = {
        'branch_no': None,
        'branch_no_raw': '',
        'patient_id': '',
        'relation_kind': '',
        'surname': '',
        'given_name': '',
        'kana_surname': '',
        'kana_given_name': '',
        'relationship_label': '',
        'occupation_label': '',
        'position_label': '',
        'is_active': None,
    }
    for raw_key, raw_value in raw_row.items():
        key = header_aliases.get(str(raw_key or '').strip().lower())
        if not key:
            key = header_aliases.get(str(raw_key or '').strip())
        value = str(raw_value or '').strip()
        if not key or not value:
            continue
        if key == 'kana_full_name':
            kana_surname, kana_given_name = _split_name_value(value)
            if kana_surname and not normalized['kana_surname']:
                normalized['kana_surname'] = kana_surname
            if kana_given_name and not normalized['kana_given_name']:
                normalized['kana_given_name'] = kana_given_name
            continue
        if key == 'is_active':
            normalized['is_active'] = _normalize_patient_linked_is_active(value)
            continue
        if key == 'branch_no':
            normalized['branch_no_raw'] = value
            normalized['branch_no'] = _normalize_branch_no_value(value)
            continue
        if key == 'relation_kind':
            normalized['relation_kind'] = _normalize_relation_kind_value(value) or ''
            continue
        normalized[key] = value
    return normalized


def _patient_linked_person_sort_queryset(queryset, sort_key: str, id_field: str):
    sort_key = str(sort_key or id_field).strip() or id_field
    if sort_key == 'linked_person_code':
        return queryset.order_by('linked_person_code', 'patient_id', 'branch_no')
    if sort_key == 'kana':
        return queryset.order_by('kana_surname', 'kana_given_name', 'patient_id', 'branch_no')
    if sort_key == 'patient_id':
        return queryset.order_by('patient_id', 'branch_no')
    if sort_key == 'branch_no':
        return queryset.order_by('patient_id', 'branch_no')
    if sort_key == 'relation_kind':
        kind_order = Case(
            When(relation_kind='family', then=Value(0)),
            When(relation_kind='guardian', then=Value(1)),
            default=Value(2),
            output_field=IntegerField(),
        )
        return queryset.annotate(_kind_order=kind_order).order_by('_kind_order', 'patient_id', 'branch_no')
    if sort_key == 'relationship_label':
        return queryset.order_by('relationship_label', 'patient_id', 'branch_no')
    if sort_key == 'is_active':
        active_order = Case(
            When(is_active=True, then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        )
        return queryset.annotate(_active_order=active_order).order_by('_active_order', 'patient_id', 'branch_no')
    if sort_key == 'updated_at':
        return queryset.order_by('-updated_at', 'patient_id', 'branch_no')
    return queryset.order_by('patient_id', 'branch_no')


def _patient_linked_person_upsert_from_csv_row(
    model_cls,
    normalized_row: dict[str, object],
    *,
    default_relation_kind: str = 'family',
) -> tuple[object | None, bool, bool]:
    branch_no = _normalize_branch_no_value(normalized_row.get('branch_no'))
    if branch_no is None:
        return None, False, False

    patient_id = str(normalized_row.get('patient_id') or '').strip()
    if not patient_id or not Patient.objects.filter(patient_id=patient_id).exists():
        return None, False, False

    defaults: dict[str, object] = {}
    relation_kind = _normalize_relation_kind_value(normalized_row.get('relation_kind')) or _normalize_relation_kind_value(default_relation_kind) or 'family'
    defaults['relation_kind'] = relation_kind
    for field_name in ('patient_id', 'surname', 'given_name', 'kana_surname', 'kana_given_name', 'relationship_label'):
        value = str(normalized_row.get(field_name) or '').strip()
        if value:
            defaults[field_name] = value
    is_active = normalized_row.get('is_active')
    if is_active is not None:
        defaults['is_active'] = bool(is_active)

    record, created = model_cls.objects.get_or_create(patient_id=patient_id, branch_no=branch_no, defaults=defaults)
    if created:
        return record, True, bool(defaults)

    changed_fields: list[str] = []
    for field_name, value in defaults.items():
        if getattr(record, field_name) != value:
            setattr(record, field_name, value)
            changed_fields.append(field_name)
    if changed_fields:
        record.save(update_fields=changed_fields + ['updated_at'])
    return record, False, bool(changed_fields)


def _next_patient_linked_branch_no(model_cls, patient_id: str, used_branch_nos: set[int]) -> int:
    latest_branch_no = (
        model_cls.objects.filter(patient_id=patient_id)
        .order_by('-branch_no')
        .values_list('branch_no', flat=True)
        .first()
    )
    branch_no = int(latest_branch_no or 0) + 1
    while branch_no in used_branch_nos:
        branch_no += 1
    return branch_no


def _import_patient_linked_csv(
    uploaded_file,
    *,
    model_cls,
    header_aliases: dict[str, str],
    record_label: str,
    header_example: str,
    default_relation_kind: str = 'family',
) -> dict[str, int]:
    csv_text = _decode_patient_csv_file(uploaded_file)
    reader = csv.DictReader(StringIO(csv_text))
    created_count = 0
    updated_count = 0
    skipped_count = 0
    seen_ids: set[str] = set()
    used_branch_nos_by_patient: dict[str, set[int]] = {}

    with transaction.atomic():
        for raw_row in reader:
            normalized_row = _normalize_linked_person_csv_row(raw_row, header_aliases)
            patient_id = str(normalized_row.get('patient_id') or '').strip()
            if not patient_id or not Patient.objects.filter(patient_id=patient_id).exists():
                skipped_count += 1
                continue

            patient_used_branch_nos = used_branch_nos_by_patient.setdefault(patient_id, set())
            branch_no = _normalize_branch_no_value(normalized_row.get('branch_no'))
            if branch_no is None:
                raw_branch_no = str(normalized_row.get('branch_no_raw') or '').strip()
                if raw_branch_no:
                    skipped_count += 1
                    continue
                branch_no = _next_patient_linked_branch_no(model_cls, patient_id, patient_used_branch_nos)
                normalized_row['branch_no'] = branch_no
            patient_used_branch_nos.add(branch_no)

            record, created, changed = _patient_linked_person_upsert_from_csv_row(
                model_cls,
                normalized_row,
                default_relation_kind=default_relation_kind,
            )
            if record is None:
                skipped_count += 1
                continue
            if created:
                created_count += 1
            elif changed:
                updated_count += 1
            else:
                skipped_count += 1
            seen_ids.add(f"{getattr(record, 'patient_id', '')}:{getattr(record, 'branch_no', '')}")

    if not seen_ids:
        raise ValueError(
            f'有効な{record_label}データの枝番が見つかりませんでした。'
            f'CSVの1行目が `{header_example}` になっているか、'
            'Excelファイルをそのまま選んでいないか確認してください。'
        )

    return {
        'created': created_count,
        'updated': updated_count,
        'skipped': skipped_count,
        'processed': created_count + updated_count,
        'unique_ids': len(seen_ids),
    }


def _checkbox_group_fields_for_template(template_type: str) -> list[dict[str, object]]:
    return [
        field
        for field in get_template_input_schema(template_type)
        if str(field.get('key') or '')
    ]


def _field_rows_for_template(template_type: str) -> list[dict[str, object]]:
    schema = get_template_input_schema(template_type)
    existing_rows = {
        row.field_key: row
        for row in TemplateInputField.objects.filter(template_type=template_type)
    }
    rows: list[dict[str, object]] = []
    for index, field in enumerate(schema):
        field_key = str(field.get('key') or '')
        row = existing_rows.get(field_key)
        raw_input_type = str(field.get('input_type') or 'textarea').strip() or 'textarea'
        has_checkbox_options = bool(field.get('options')) or raw_input_type == 'checkbox_group'
        input_type = 'checkbox_group' if has_checkbox_options else (raw_input_type if raw_input_type in FIELD_INPUT_TYPE_VALUES else 'textarea')
        rows.append({
            'row_key': field_key,
            'record_id': str(row.pk) if row else '',
            'field_key': field_key,
            'source_kind': 'db' if row else 'builtin',
            'label': str(field.get('label') or field_key),
            'input_type': input_type,
            'section_title': str(field.get('section_title') or ''),
            'required': bool(field.get('required')),
            'allow_other': bool(field.get('allow_other')) if has_checkbox_options else False,
            'other_label': str(field.get('other_label') or 'その他'),
            'other_placeholder': str(field.get('other_placeholder') or '自由入力'),
            'help_text': str(field.get('help_text') or ''),
            'textarea_rows': _safe_int(field.get('textarea_rows'), default=3),
            'position': _safe_int(field.get('sort_order'), default=index * 10),
            'has_checkbox_options': has_checkbox_options,
            'option_count': len(field.get('options') or []),
        })
    return rows


def _parse_template_field_rows(post_data) -> list[dict[str, object]]:
    prefix = 'field__'
    row_payloads: dict[str, dict[str, object]] = {}
    for key, value in post_data.items():
        if not key.startswith(prefix):
            continue
        remainder = key[len(prefix):]
        if '__' not in remainder:
            continue
        row_key, attr = remainder.split('__', 1)
        row_payloads.setdefault(row_key, {'row_key': row_key})[attr] = value

    parsed_rows: list[dict[str, object]] = []
    for order, row_key in enumerate(row_payloads):
        payload = row_payloads[row_key]
        input_type = str(payload.get('input_type') or 'textarea').strip() or 'textarea'
        parsed_rows.append({
            'row_key': row_key,
            'record_id': str(payload.get('record_id') or '').strip(),
            'field_key': str(payload.get('field_key') or '').strip(),
            'source_kind': str(payload.get('source_kind') or 'new').strip() or 'new',
            'label': str(payload.get('label') or '').strip(),
            'input_type': input_type,
            'section_title': str(payload.get('section_title') or '').strip(),
            'required': bool(_is_truthy(payload.get('required'))),
            'allow_other': bool(_is_truthy(payload.get('allow_other'))),
            'other_label': str(payload.get('other_label') or '').strip(),
            'other_placeholder': str(payload.get('other_placeholder') or '').strip(),
            'help_text': str(payload.get('help_text') or '').strip(),
            'textarea_rows': max(1, _safe_int(payload.get('textarea_rows'), default=3)),
            'position': _safe_int(payload.get('position'), default=order * 10),
            'order': order,
        })
    return parsed_rows


def _parse_deleted_template_field_keys(post_data) -> list[str]:
    raw = str(post_data.get('deleted_field_keys') or '').strip()
    if not raw:
        return []
    keys = []
    seen: set[str] = set()
    for item in raw.split(','):
        key = str(item).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        keys.append(key)
    return keys


def _generate_template_field_key(existing_keys: set[str]) -> str:
    while True:
        candidate = f'custom_{uuid.uuid4().hex[:8]}'
        if candidate not in existing_keys:
            return candidate


def _next_new_template_field_row_number(parsed_rows: list[dict[str, object]]) -> int:
    next_row_number = 0
    for row in parsed_rows:
        row_key = str(row.get('row_key') or '')
        if not row_key.startswith('new_'):
            continue
        try:
            next_row_number = max(next_row_number, int(row_key.split('_', 1)[1]) + 1)
        except Exception:
            next_row_number += 1
    return next_row_number


def _template_field_editor_context(
    template_type: str,
    *,
    parsed_rows: list[dict[str, object]] | None = None,
    field_errors: dict[str, str] | None = None,
    deleted_field_keys: list[str] | None = None,
) -> list[dict[str, object]]:
    field_errors = field_errors or {}
    deleted_field_keys = deleted_field_keys or []
    if parsed_rows is None:
        rows = _field_rows_for_template(template_type)
    else:
        rows = []
        for row in parsed_rows:
            input_type = str(row.get('input_type') or 'textarea')
            rows.append({
                'row_key': str(row.get('row_key') or ''),
                'record_id': str(row.get('record_id') or ''),
                'field_key': str(row.get('field_key') or ''),
                'source_kind': str(row.get('source_kind') or 'new'),
                'label': str(row.get('label') or ''),
                'input_type': input_type,
                'section_title': str(row.get('section_title') or ''),
                'required': bool(row.get('required')),
                'allow_other': bool(row.get('allow_other')),
                'other_label': str(row.get('other_label') or 'その他'),
                'other_placeholder': str(row.get('other_placeholder') or '自由入力'),
                'help_text': str(row.get('help_text') or ''),
                'textarea_rows': max(1, _safe_int(row.get('textarea_rows'), default=3)),
                'position': _safe_int(row.get('position'), default=0),
                'has_checkbox_options': input_type == 'checkbox_group',
                'option_count': 0,
                'error': field_errors.get(str(row.get('row_key') or ''), ''),
                'is_deleted': False,
            })
        return rows

    for row in rows:
        row['error'] = field_errors.get(str(row.get('row_key') or ''), '')
        row['is_deleted'] = str(row.get('field_key') or '') in deleted_field_keys
    return rows


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


def _is_truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def _load_checkbox_group_rows(field: dict[str, object], group: TemplateInputCheckboxGroup | None) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if group is not None:
        for option in group.options.all():
            text = str(getattr(option, 'text', '') or '').strip()
            if not text:
                continue
            rows.append({
                'row_key': f'opt_{option.pk}',
                'id': str(option.pk),
                'text': text,
                'position': int(getattr(option, 'sort_order', 0) or 0),
            })
        return rows

    for index, option in enumerate(field.get('options') or []):
        if isinstance(option, dict):
            text = str(option.get('label') or option.get('value') or '').strip()
        else:
            text = str(option or '').strip()
        if not text:
            continue
        rows.append({
            'row_key': f'fallback_{index}',
            'id': '',
            'text': text,
            'position': index * 10,
        })
    return rows


def _parse_checkbox_group_rows(post_data, field_key: str) -> list[dict[str, object]]:
    prefix = f'checkbox__{field_key}__'
    row_payloads: dict[str, dict[str, object]] = {}
    for key, value in post_data.items():
        if not key.startswith(prefix):
            continue
        remainder = key[len(prefix):]
        if '__' not in remainder:
            continue
        row_key, attr = remainder.split('__', 1)
        row_payloads.setdefault(row_key, {'row_key': row_key})[attr] = value

    parsed_rows: list[dict[str, object]] = []
    for order, row_key in enumerate(row_payloads):
        payload = row_payloads[row_key]
        parsed_rows.append({
            'row_key': row_key,
            'id': str(payload.get('id') or '').strip(),
            'text': str(payload.get('text') or '').strip(),
            'position': _safe_int(payload.get('position'), default=order * 10),
            'order': order,
        })
    return parsed_rows


def _build_checkbox_group_field_context(
    field: dict[str, object],
    group: TemplateInputCheckboxGroup | None,
    rows: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    key = str(field.get('key') or '')
    label = str(field.get('label') or key)
    if rows is None:
        rows = _load_checkbox_group_rows(field, group)
    next_position = 10
    if rows:
        next_position = max(int(row.get('position') or 0) for row in rows) + 10
    return {
        'key': key,
        'label': label,
        'help_text': str(field.get('help_text') or ''),
        'allow_other': bool(field.get('allow_other')),
        'other_label': str(field.get('other_label') or 'その他'),
        'rows': rows,
        'has_rows': bool(rows),
        'next_row_number': len(rows),
        'next_position': next_position,
        'group_exists': group is not None,
    }


def _log_operation(
    request,
    action: str,
    target_type: str = '',
    target_id: str = '',
    details: dict | None = None,
    result: str = 'success',
    error_message: str = '',
) -> None:
    user = request.user
    source_ip = get_client_ip(request) or None
    OperationLog.objects.create(
        actor=user if user.is_authenticated else None,
        actor_username=user.get_username() if user.is_authenticated else '',
        action=action,
        target_type=target_type,
        target_id=target_id,
        source_ip=source_ip,
        import_source_ip=source_ip if 'import' in action else None,
        result=result,
        error_message=error_message,
        details=details or {},
    )


def _current_template_source_filenames() -> set[str]:
    return {source.source_filename for source in list_template_sources()}


def _managed_template_queryset():
    source_filenames = _current_template_source_filenames()
    return Template.objects.filter(source_filename__in=source_filenames)


def _normalize_template_sort_order(templates: list[Template] | None = None) -> list[Template]:
    if templates is None:
        templates = list(_managed_template_queryset().order_by('sort_order', 'template_type', 'name', 'id'))

    if not templates:
        return []

    now = timezone.now()
    changed_templates: list[Template] = []
    for index, template in enumerate(templates, start=1):
        if template.sort_order != index:
            template.sort_order = index
            template.updated_at = now
            changed_templates.append(template)

    if changed_templates:
        Template.objects.bulk_update(changed_templates, ['sort_order', 'updated_at'])

    return templates


def _prompt_text_from_payload(payload: dict) -> str:
    return (
        payload.get('prompt_text')
        or payload.get('prompt')
        or payload.get('content', {}).get('text')
        or json.dumps(payload, ensure_ascii=False, indent=2)
    )


_LOCAL_ONLY_PROMPT_JSON_KEYS = {
    'audio_data',
    'audio_file',
    'audio_file_name',
    'audio_filename',
    'audio_name',
    'audio_blob',
    'original_text',
    'raw_text',
    'source_input_data',
    'source_text',
    'transcript_text',
    'transcript_source',
    'voice_audio',
    'voice_file',
    'voice_file_name',
}
_LOCAL_ONLY_PROMPT_JSON_PREFIXES = (
    'audio_',
    'voice_',
)


def _sanitize_prompt_payload_for_dmz(value):
    if isinstance(value, dict):
        sanitized = {}
        for key, child in value.items():
            key_name = str(key)
            key_lower = key_name.lower()
            if key_lower in _LOCAL_ONLY_PROMPT_JSON_KEYS or any(key_lower.startswith(prefix) for prefix in _LOCAL_ONLY_PROMPT_JSON_PREFIXES):
                continue
            sanitized[key] = _sanitize_prompt_payload_for_dmz(child)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_prompt_payload_for_dmz(item) for item in value]
    return value


def _safe_token(value: str) -> str:
    token = re.sub(r'[\\/\s]+', '_', value.strip())
    token = re.sub(r'[^\w.\-（）()ぁ-んァ-ヶ一-龥ー]', '_', token)
    return token.strip('._') or 'template'


def _make_prompt_source_id(template_name: str) -> str:
    return f'prompt_{_safe_token(template_name)}_{uuid.uuid4().hex[:8]}'


def _selected_template_name(form: AnonymizeForm) -> str:
    choices = [choice[0] for choice in form.fields.get('template').choices]
    if form.is_bound:
        candidate = str(form.data.get('template') or '').strip()
        if candidate in choices:
            return candidate
    initial_template = str(form.initial.get('template') or '').strip()
    if initial_template in choices:
        return initial_template
    return choices[0] if choices else ''


def _selected_input_mode(form: AnonymizeForm) -> str:
    valid_modes = [choice[0] for choice in form.fields.get('input_mode').choices]
    if form.is_bound:
        candidate = str(form.data.get('input_mode') or 'free').strip()
        if candidate in valid_modes:
            return candidate
    initial_mode = str(form.initial.get('input_mode') or 'free').strip()
    if initial_mode in valid_modes:
        return initial_mode
    return 'free'


def _structured_field_context(
    template_type: str,
    structured_input: dict[str, object] | None = None,
    errors: dict[str, str] | None = None,
) -> list[dict[str, object]]:
    structured_input = normalize_structured_input(template_type, structured_input or {})
    errors = errors or {}
    fields = []
    for field in get_template_input_schema(template_type):
        key = str(field['key'])
        input_type = str(field.get('input_type') or 'textarea')
        has_checkbox_options = bool(field.get('options')) or input_type == 'checkbox_group'
        if key in structured_input:
            value = structured_input.get(key)
        elif has_checkbox_options:
            default_text = str(field.get('default', '') or '').strip()
            value = {
                'text': default_text,
                'selected': [],
                'other': '',
                'other_checked': False,
            }
        else:
            value = str(field.get('default', '') or '')
        if has_checkbox_options:
            value_map = value if isinstance(value, dict) else {
                'text': str(value or ''),
                'selected': [],
                'other': '',
                'other_checked': False,
            }
            text_value = str(value_map.get('text') or '')
            selected_values = list(value_map.get('selected') or [])
            other_text = str(value_map.get('other') or '')
            other_checked = bool(value_map.get('other_checked'))
        else:
            text_value = ''
            selected_values = []
            other_text = ''
            other_checked = False
        fields.append({
            **field,
            'value': value,
            'has_checkbox_options': has_checkbox_options,
            'text_value': text_value,
            'selected_values': selected_values,
            'other_text': other_text,
            'other_checked': other_checked,
            'error': errors.get(key, ''),
        })
    return fields


def _anonymize_page_context(
    form: AnonymizeForm,
    *,
    template_type: str,
    input_mode: str,
    source_text: str = '',
    structured_input: dict[str, object] | None = None,
    structured_field_errors: dict[str, str] | None = None,
    structured_fields: list[dict[str, object]] | None = None,
    text_items: list[dict[str, object]] | None = None,
    restore_map: dict[str, str] | None = None,
    prompt_json: str = '',
    restore_json: str = '',
    source_id: str = '',
    patient_profile: dict[str, object] | None = None,
    show_patient_panel: bool | None = None,
) -> dict[str, object]:
    structured_fields = structured_fields or _structured_field_context(template_type, structured_input, structured_field_errors)
    restore_map = restore_map or {}
    patient_profile = patient_profile or {}
    resolved_show_patient_panel = _template_supports_patient_master(template_type) if show_patient_panel is None else show_patient_panel
    return {
        'form': form,
        'template_type': template_type,
        'input_mode': input_mode,
        'source_text': source_text,
        'structured_fields': structured_fields,
        'structured_input': structured_input or {},
        'structured_field_errors': structured_field_errors or {},
        'text_items': text_items or [],
        'restore_map': restore_map,
        'restore_map_items': list(restore_map.items()),
        'prompt_json': prompt_json,
        'restore_json': restore_json,
        'source_id': source_id,
        'patient_profile': patient_profile,
        'patient_id': str(patient_profile.get('patient_id') or form.initial.get('patient_id') or form.data.get('patient_id') or '').strip(),
        'show_patient_panel': resolved_show_patient_panel,
        'patient_lookup_url_template': reverse('close_side:patient_lookup', kwargs={'patient_id': '__PATIENT_ID__'}),
        'template_input_schemas': get_template_input_schema_map(),
    }


def _metadata_for_user(source_id: str, user):
    return _owned_queryset(RestoreMetadata.objects.all(), user).filter(source_id=source_id).first()


def _build_result_preview(
    result_record: RestoredResult,
    *,
    patient_profile: dict[str, object] | None = None,
) -> dict[str, object]:
    result_text = _prepend_blank_lines_for_patient_basic_info(
        result_record.result_text or '',
        result_record.template_type or '',
        patient_profile,
    )
    restored_text = result_record.restored_text or ''
    has_result_text = bool(result_text.strip())
    restored_display_text = _prepend_patient_basic_info_to_restored_text(
        restored_text,
        result_record.template_type or '',
        patient_profile,
    )
    has_restored_text = bool(restored_display_text.strip())
    result_json = result_record.result_json if isinstance(result_record.result_json, dict) else {}
    input_mode = result_json.get('metadata', {}).get('input_mode') or ''

    if has_result_text and has_restored_text:
        result_html, restored_html = highlight_changed_text(result_text, restored_display_text)
    else:
        result_html = mark_safe(escape(result_text)) if has_result_text else ''
        restored_html = mark_safe(escape(restored_display_text)) if has_restored_text else ''

    return {
        'imported_filename': result_record.imported_filename or '',
        'source_id': result_record.source_id or '',
        'result_id': result_record.result_id or '',
        'template_type': result_record.template_type or '',
        'status_label': result_record.get_status_display(),
        'status': result_record.status,
        'reviewer': result_record.reviewer or '',
        'input_mode': input_mode,
        'created_at': result_record.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        'updated_at': result_record.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
        'result_text': result_text,
        'restored_text': restored_display_text,
        'result_html': result_html,
        'restored_html': restored_html,
        'has_result_text': has_result_text,
        'has_restored_text': has_restored_text,
    }


def _normalize_restore_label_rows(raw_rows: object) -> list[dict[str, str]]:
    if isinstance(raw_rows, str):
        raw_rows = raw_rows.strip()
        if not raw_rows:
            return []
        try:
            raw_rows = json.loads(raw_rows)
        except json.JSONDecodeError as exc:
            raise ValueError('復元ラベルの JSON を解析できません。') from exc

    if isinstance(raw_rows, dict):
        raw_rows = raw_rows.get('rows') or raw_rows.get('items') or []

    if not isinstance(raw_rows, list):
        raise ValueError('復元ラベルは配列で指定してください。')

    rows: list[dict[str, str]] = []
    for item in raw_rows:
        if not isinstance(item, dict):
            continue
        rows.append({
            'old_label': str(item.get('old_label') or '').strip(),
            'label': str(item.get('label') or '').strip(),
            'original': str(item.get('original') or '').strip(),
        })
    return rows


def _restore_map_from_rows(rows: list[dict[str, str]]) -> dict[str, str]:
    restore_map: dict[str, str] = {}
    for row in rows:
        label = str(row.get('label') or '').strip()
        original = str(row.get('original') or '').strip()
        if label and original:
            restore_map[label] = original
    return restore_map


def _apply_restore_label_renames(result_text: str, rows: list[dict[str, str]]) -> str:
    updated_text = result_text or ''
    replacements = [
        (str(row.get('old_label') or '').strip(), str(row.get('label') or '').strip())
        for row in rows
        if str(row.get('old_label') or '').strip() and str(row.get('label') or '').strip()
    ]
    for old_label, new_label in sorted(replacements, key=lambda item: len(item[0]), reverse=True):
        if old_label != new_label:
            updated_text = updated_text.replace(old_label, new_label)
    return updated_text


def _result_json_display_payload(result_record: RestoredResult, result_text: str) -> dict[str, object]:
    payload = deepcopy(result_record.result_json) if isinstance(result_record.result_json, dict) else {}
    if not isinstance(payload, dict):
        payload = {}
    if not payload:
        payload = {
            'id': f'result_{result_record.source_id}' if result_record.source_id else '',
            'source_id': result_record.source_id or '',
            'result_text': result_text,
            'metadata': {},
        }
    else:
        payload['result_text'] = result_text
        payload.setdefault('source_id', result_record.source_id or '')
    return payload


def _restored_result_page_context(
    request,
    result_record: RestoredResult,
    *,
    metadata: RestoreMetadata,
    filename: str | None = None,
    restore_map: dict[str, str] | None = None,
    result_text: str | None = None,
    restored_text: str | None = None,
) -> dict[str, object]:
    current_result_text = result_text if result_text is not None else (result_record.result_text or '')
    current_restored_text = restored_text if restored_text is not None else (result_record.restored_text or '')
    current_restore_map = restore_map if restore_map is not None else (metadata.restore_map or {})
    patient_profile = _patient_profile_for_source_id(result_record.source_id, request.user)
    display_restore_map = _augment_restore_map_with_patient_info(current_restore_map, patient_profile)
    if current_result_text.strip():
        current_restored_text = restore_text(current_result_text, display_restore_map)
    current_result_text = _prepend_blank_lines_for_patient_basic_info(
        current_result_text,
        result_record.template_type or metadata.template_type or '',
        patient_profile,
    )
    current_restored_text = _prepend_patient_basic_info_to_restored_text(
        current_restored_text,
        result_record.template_type or metadata.template_type or '',
        patient_profile,
    )

    if current_result_text.strip() and current_restored_text.strip():
        result_html, restored_html = highlight_changed_text(current_result_text, current_restored_text)
    else:
        result_html = mark_safe(escape(current_result_text)) if current_result_text.strip() else ''
        restored_html = mark_safe(escape(current_restored_text)) if current_restored_text.strip() else ''

    result_json_payload = _result_json_display_payload(result_record, current_result_text)
    input_mode = ''
    if isinstance(result_record.result_json, dict):
        result_metadata = result_record.result_json.get('metadata')
        if isinstance(result_metadata, dict):
            input_mode = str(result_metadata.get('input_mode') or '')

    return {
        'record': result_record,
        'filename': filename or result_record.imported_filename or '',
        'source_id': result_record.source_id or '',
        'template_type': result_record.template_type or metadata.template_type,
        'input_mode': input_mode,
        'result_text': current_result_text,
        'restored_text': current_restored_text,
        'result_html': result_html,
        'restored_html': restored_html,
        'result_json': json.dumps(result_json_payload, ensure_ascii=False, indent=2),
        'restore_map_items': list(display_restore_map.items()),
        'patient_display_label': _patient_display_label(patient_profile),
    }


def _result_history_list_context(request) -> dict[str, object]:
    history_query = request.GET.get('q', '').strip()
    saved_results = list(_owned_queryset(RestoredResult.objects.all(), request.user).order_by('-created_at')[:HISTORY_LIMIT])
    saved_results = filter_history_items(saved_results, history_query, [
        'imported_filename',
        'result_id',
        'source_id',
        'template_type',
        'status',
        lambda item: item.get_status_display(),
        'reviewer',
        lambda item: item.owner.get_username() if item.owner else '',
        lambda item: item.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        lambda item: item.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
    ])
    return {
        'history_query': history_query,
        'saved_results': saved_results,
    }


def _result_history_preview_context(request, pk: int) -> dict[str, object]:
    history_query = request.GET.get('q', '').strip()
    selected_result = get_object_or_404(_owned_queryset(RestoredResult.objects.all(), request.user), pk=pk)
    selected_preview = _build_result_preview(
        selected_result,
        patient_profile=_patient_profile_for_source_id(selected_result.source_id, request.user),
    )
    selected_preview['patient_display_label'] = _patient_display_label(
        _patient_profile_for_source_id(selected_result.source_id, request.user)
    )
    return {
        'history_query': history_query,
        'selected_result': selected_result,
        'selected_preview': selected_preview,
    }


def highlight_changed_text(original: str, anonymized: str) -> tuple[str, str]:
    matcher = difflib.SequenceMatcher(None, original, anonymized)
    original_html = []
    anonymized_html = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            original_html.append(escape(original[i1:i2]))
            anonymized_html.append(escape(anonymized[j1:j2]))
        else:
            if i1 < i2:
                original_html.append(
                    f'<span class="anonymized-label changed">{escape(original[i1:i2])}</span>'
                )
            if j1 < j2:
                anonymized_html.append(
                    f'<span class="anonymized-label changed">{escape(anonymized[j1:j2])}</span>'
                )

    return mark_safe(''.join(original_html)), mark_safe(''.join(anonymized_html))


def _close_to_open_dir() -> Path:
    return Path(__file__).resolve().parents[2] / 'dmz' / 'close_to_open'


def _open_to_close_dir() -> Path:
    return Path(__file__).resolve().parents[2] / 'dmz' / 'open_to_close'


def _safe_filename(filename: str) -> str:
    safe_name = Path(filename).name
    if safe_name != filename:
        raise ValueError('不正なファイル名です')
    return safe_name


def _prompt_json_filename(source_id: str) -> str:
    file_stem = source_id if source_id.startswith('prompt_') else f'prompt_{source_id}'
    return f'{_safe_token(file_stem)}.json'


def _payload_visible_to_user(payload: dict, user) -> bool:
    if _is_admin(user):
        return True
    metadata = payload.get('metadata') or {}
    owner_user_id = metadata.get('owner_user_id')
    owner_username = metadata.get('owner_username')
    if owner_user_id:
        return str(owner_user_id) == str(user.id)
    if owner_username:
        return owner_username == user.get_username()
    return False


def _read_json_file(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def _list_files(directory: Path, user=None):
    if not directory.exists():
        return []

    files = []
    entries = sorted(directory.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    for entry in entries:
        if entry.is_file():
            payload = _read_json_file(entry)
            if user is not None and not _payload_visible_to_user(payload, user):
                continue
            metadata = payload.get('metadata') or {}
            stat = entry.stat()
            files.append({
                'name': entry.name,
                'size': stat.st_size,
                'modified': datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                'source_id': payload.get('source_id') or metadata.get('source_id') or '',
                'owner_username': metadata.get('owner_username') or '',
            })
    return files


def menu(request):
    recent_prompts = _owned_queryset(Prompt.objects.all(), request.user).order_by('-updated_at')[:5]
    recent_results = _owned_queryset(RestoredResult.objects.all(), request.user).order_by('-created_at')[:5]
    return render(request, 'anonymizer_app/close_menu.html', {
        'recent_prompts': recent_prompts,
        'recent_results': recent_results,
    })


def home(request):
    if request.method == 'GET':
        reload_prompt_id = str(request.GET.get('reload_prompt_id') or '').strip()
        if reload_prompt_id:
            prompt = get_object_or_404(_owned_queryset(Prompt.objects.all(), request.user), pk=reload_prompt_id)
            source_input_data = normalize_source_input_data(prompt.source_input_data)
            template_name = str(source_input_data.get('template_type') or '').strip()
            input_mode = str(source_input_data.get('input_mode') or 'free').strip() or 'free'
            structured_input = source_input_data.get('structured_input') or {}
            if not isinstance(structured_input, dict):
                structured_input = {}
            patient_profile = source_input_data.get('patient') or {}
            if not isinstance(patient_profile, dict):
                patient_profile = {}
            source_text = build_source_text_from_source_input_data(prompt.source_input_data)
            transcript_source = str(source_input_data.get('transcript_source') or 'manual_input').strip() or 'manual_input'
            form = AnonymizeForm(initial={
                'template': template_name,
                'input_mode': input_mode,
                'text': source_text if input_mode != 'voice' else '',
                'transcript_text': source_text if input_mode == 'voice' else '',
                'transcript_source': transcript_source if input_mode == 'voice' else 'manual_input',
                'patient_id': str(source_input_data.get('patient_id') or patient_profile.get('patient_id') or '').strip(),
            })
            return render(request, 'anonymizer_app/index.html', _anonymize_page_context(
                form,
                template_type=template_name,
                input_mode=input_mode,
                source_text=source_text,
                structured_input=structured_input if input_mode == 'structured' else {},
                structured_fields=_structured_field_context(
                    template_name,
                    structured_input if input_mode == 'structured' else {},
                ),
                patient_profile=patient_profile,
            ))

    form = AnonymizeForm(request.POST or None)
    template_name = _selected_template_name(form)
    input_mode = _selected_input_mode(form)
    structured_input: dict[str, object] = {}
    structured_field_errors: dict[str, str] = {}
    source_text = ''
    patient_profile: dict[str, object] = {}

    if request.method == 'POST' and form.is_valid():
        template_name = form.cleaned_data['template']
        input_mode = form.cleaned_data.get('input_mode') or 'free'
        transcript_source = 'manual_input'
        patient_id = str(form.cleaned_data.get('patient_id') or '').strip()
        patient_record = _patient_for_patient_id(patient_id) if _template_supports_patient_master(template_name) and patient_id else None
        if _template_supports_patient_master(template_name) and patient_id and patient_record is None:
            form.add_error('patient_id', f'患者ID {patient_id} が見つかりません。')
            invalid_structured_input: dict[str, object] = {}
            if input_mode == 'structured':
                invalid_structured_input = collect_structured_input(template_name, request.POST)
            return render(request, 'anonymizer_app/index.html', _anonymize_page_context(
                form,
                template_type=template_name,
                input_mode=input_mode,
                source_text=build_source_text_from_structured_input(template_name, invalid_structured_input) if input_mode == 'structured' else '',
                structured_input=invalid_structured_input,
                structured_fields=_structured_field_context(template_name, invalid_structured_input),
                patient_profile={'patient_id': patient_id},
            ))
        patient_profile = _patient_payload(patient_record)

        if input_mode == 'structured':
            structured_input = collect_structured_input(template_name, request.POST)
            structured_field_errors = validate_structured_input(template_name, structured_input)
            source_text = build_source_text_from_structured_input(template_name, structured_input)
            if structured_field_errors:
                return render(request, 'anonymizer_app/index.html', _anonymize_page_context(
                    form,
                    template_type=template_name,
                    input_mode=input_mode,
                    source_text=source_text,
                    structured_input=structured_input,
                    structured_field_errors=structured_field_errors,
                    patient_profile=patient_profile,
                ))
        elif input_mode == 'voice':
            source_text = (form.cleaned_data.get('transcript_text') or '').strip()
            transcript_source = str(form.cleaned_data.get('transcript_source') or 'manual_input').strip() or 'manual_input'
            if not source_text:
                form.add_error('transcript_text', '文字起こし結果が空です。録音または入力してください。')
                return render(request, 'anonymizer_app/index.html', _anonymize_page_context(
                    form,
                    template_type=template_name,
                    input_mode=input_mode,
                    source_text=source_text,
                    patient_profile=patient_profile,
                ))
        else:
            source_text = (form.cleaned_data.get('text') or '').strip()
            if not source_text:
                form.add_error('text', '入力文章を入力してください。')
                return render(request, 'anonymizer_app/index.html', _anonymize_page_context(
                    form,
                    template_type=template_name,
                    input_mode=input_mode,
                    source_text=source_text,
                    patient_profile=patient_profile,
                ))

        preferred_entity_groups = _preferred_entity_groups_for_anonymization(
            patient_record if _template_supports_patient_master(template_name) else None
        )
        result = anonymize_text(
            source_text,
            template_name,
            preferred_entity_groups=preferred_entity_groups,
        )
        anonymized_text = result.text
        restore_map = _augment_restore_map_with_patient_info(result.restore_map, patient_profile)

        source_id = _make_prompt_source_id(template_name)
        payload = build_prompt_payload(
            template_name,
            {'text': anonymized_text},
            source_id,
            title=template_name,
            patient_profile=patient_profile or None,
        )
        payload['metadata']['created_at'] = None
        payload['metadata']['owner_user_id'] = request.user.id
        payload['metadata']['owner_username'] = request.user.get_username()
        payload['metadata']['template_name'] = template_name
        payload['metadata']['input_mode'] = input_mode
        if input_mode == 'structured':
            payload['metadata']['structured_input_labels'] = build_structured_input_labels(template_name, structured_input)
        source_input_data = build_source_input_data(
            template_name,
            input_mode,
            source_text,
            structured_input,
            transcript_source=transcript_source if input_mode == 'voice' else '',
            patient=patient_profile or None,
        )
        payload = _sanitize_prompt_payload_for_dmz(payload)
        restore_data = {
            'source_id': source_id,
            'restore_map': restore_map,
        }
        original_html, anonymized_html = highlight_changed_text(source_text, anonymized_text)
        text_items = [{
            'label': '入力テキスト',
            'original': source_text,
            'anonymized': anonymized_text,
            'original_html': original_html,
            'anonymized_html': anonymized_html,
        }]

        RestoreMetadata.objects.create(
            source_id=source_id,
            template_type=template_name,
            restore_map=restore_map,
            prompt_json=payload,
            owner=request.user,
            status='draft',
        )
        Prompt.objects.update_or_create(
            source_id=source_id,
            defaults={
                'name': f'{template_name} / {source_id}',
                'content': _prompt_text_from_payload(payload),
                'source_input_data': source_input_data,
                'owner': request.user,
                'status': 'draft',
            },
        )
        _log_operation(request, 'prompt_created', 'RestoreMetadata', source_id)

        return render(request, 'anonymizer_app/index.html', _anonymize_page_context(
            form,
            template_type=template_name,
            input_mode=input_mode,
            source_text=source_text,
            structured_input=structured_input,
            structured_field_errors=structured_field_errors,
            text_items=text_items,
            restore_map=restore_map,
            prompt_json=json.dumps(payload, ensure_ascii=False, indent=2),
            restore_json=json.dumps(restore_data, ensure_ascii=False, indent=2),
            source_id=source_id,
            patient_profile=patient_profile,
        ))

    structured_fields = _structured_field_context(template_name)
    return render(request, 'anonymizer_app/index.html', _anonymize_page_context(
        form,
        template_type=template_name,
        input_mode=input_mode,
        source_text=source_text,
        structured_fields=structured_fields,
        patient_profile=patient_profile,
    ))


def download_prompt(request, source_id):
    metadata = get_object_or_404(_owned_queryset(RestoreMetadata.objects.all(), request.user), source_id=source_id)
    prompt_payload = _sanitize_prompt_payload_for_dmz(metadata.prompt_json or {})
    response = HttpResponse(
        json.dumps(prompt_payload, ensure_ascii=False, indent=2),
        content_type='application/json',
    )
    response['Content-Disposition'] = f'attachment; filename="{metadata.source_id}.json"'
    return response


def download_restore(request, source_id):
    metadata = get_object_or_404(_owned_queryset(RestoreMetadata.objects.all(), request.user), source_id=source_id)
    payload = {
        'source_id': metadata.source_id,
        'restore_map': metadata.restore_map,
    }
    response = HttpResponse(json.dumps(payload, ensure_ascii=False, indent=2), content_type='application/json')
    response['Content-Disposition'] = f'attachment; filename="restore_{metadata.source_id}.json"'
    return response


@require_http_methods(["POST"])
def update_prompt_payload(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSONとして解析できません。'}, status=400)

    source_id = str(data.get('source_id') or '').strip()
    if not source_id:
        return JsonResponse({'error': 'source_id が必要です。'}, status=400)

    metadata = _metadata_for_user(source_id, request.user)
    if metadata is None:
        return JsonResponse({'error': f'source_id {source_id} が見つかりません。'}, status=404)

    anonymized_text = str(data.get('anonymized_text') or '')
    restore_map_data = data.get('restore_map') or {}
    if not isinstance(restore_map_data, dict):
        return JsonResponse({'error': 'restore_map はオブジェクトで指定してください。'}, status=400)

    restore_map = {}
    for anonymized, original in restore_map_data.items():
        anonymized_value = str(anonymized).strip()
        if anonymized_value:
            restore_map[anonymized_value] = str(original)

    previous_restore_map = metadata.restore_map or {}
    previous_source_id = metadata.source_id
    previous_prompt_metadata = (metadata.prompt_json or {}).get('metadata', {}) if isinstance(metadata.prompt_json, dict) else {}
    template_type = str(data.get('template_type') or metadata.template_type)
    input_mode = str(data.get('input_mode') or previous_prompt_metadata.get('input_mode') or 'free')
    source_text = str(data.get('source_text') or '').strip()
    patient_id = str(data.get('patient_id') or '').strip()
    previous_prompt = _owned_queryset(Prompt.objects.all(), request.user).filter(source_id=previous_source_id).order_by('-updated_at').first()
    previous_source_input_data = normalize_source_input_data(previous_prompt.source_input_data) if previous_prompt else {}
    previous_patient_profile = previous_source_input_data.get('patient') or {}
    if not isinstance(previous_patient_profile, dict):
        previous_patient_profile = {}
    patient_record = None
    if _template_supports_patient_master(template_type):
        if patient_id:
            patient_record = _patient_for_patient_id(patient_id)
            if patient_record is None:
                return JsonResponse({'error': f'患者ID {patient_id} が見つかりません。'}, status=404)
        elif previous_patient_profile.get('patient_id'):
            patient_record = _patient_for_patient_id(str(previous_patient_profile.get('patient_id') or '').strip())
    patient_profile = _patient_payload(patient_record)
    if _template_supports_patient_master(template_type) and not patient_profile and previous_patient_profile.get('patient_id'):
        patient_profile = previous_patient_profile
    if input_mode == 'voice' and not source_text:
        return JsonResponse({'error': '文字起こし結果が空です。録音または入力してください。'}, status=400)
    structured_input_data = data.get('structured_input')
    if isinstance(structured_input_data, dict):
        structured_input = normalize_structured_input(template_type, structured_input_data)
    else:
        structured_input = {}
    if input_mode == 'structured' and not source_text:
        source_text = build_source_text_from_structured_input(template_type, structured_input)
    structured_input_labels = data.get('structured_input_labels')
    if isinstance(structured_input_labels, list):
        structured_input_labels = [str(label).strip() for label in structured_input_labels if str(label).strip()]
    else:
        structured_input_labels = []
    transcript_source = str(
        data.get('transcript_source')
        or previous_prompt_metadata.get('transcript_source')
        or 'manual_input'
    ).strip() or 'manual_input'
    if template_type != metadata.template_type:
        source_id = _make_prompt_source_id(template_type)
    source_input_data = build_source_input_data(
        template_type,
        input_mode,
        source_text,
        structured_input,
        transcript_source=transcript_source if input_mode == 'voice' else '',
        patient=patient_profile or None,
    )
    restore_map = _augment_restore_map_with_patient_info(restore_map, patient_profile)

    prompt_payload = build_prompt_payload(
        template_type,
        {'text': anonymized_text},
        source_id,
        title=template_type,
        patient_profile=patient_profile or None,
    )
    prompt_payload['metadata']['created_at'] = None
    prompt_payload['metadata']['owner_user_id'] = request.user.id
    prompt_payload['metadata']['owner_username'] = request.user.get_username()
    prompt_payload['metadata']['template_name'] = template_type
    prompt_payload['metadata']['input_mode'] = input_mode
    if structured_input_labels:
        prompt_payload['metadata']['structured_input_labels'] = structured_input_labels
    elif previous_prompt_metadata.get('structured_input_labels'):
        prompt_payload['metadata']['structured_input_labels'] = previous_prompt_metadata.get('structured_input_labels')
    prompt_payload = _sanitize_prompt_payload_for_dmz(prompt_payload)
    restore_payload = {
        'source_id': source_id,
        'restore_map': restore_map,
    }

    metadata.source_id = source_id
    metadata.template_type = template_type
    metadata.restore_map = restore_map
    metadata.prompt_json = prompt_payload
    metadata.save(update_fields=['source_id', 'template_type', 'restore_map', 'prompt_json', 'updated_at'])
    prompt_name = f'{template_type} / {source_id}'
    prompt_content = _prompt_text_from_payload(prompt_payload)
    Prompt.objects.filter(source_id=previous_source_id).update(
        source_id=source_id,
        name=prompt_name,
        content=prompt_content,
        source_input_data=source_input_data,
        updated_at=timezone.now(),
    )
    prompt = _owned_queryset(Prompt.objects.all(), request.user).filter(source_id=source_id).order_by('-updated_at').first()
    if prompt is None:
        prompt = Prompt.objects.create(
            source_id=source_id,
            name=prompt_name,
            content=prompt_content,
            source_input_data=source_input_data,
            owner=request.user,
            status='draft',
        )

    removed_labels = sorted(set(previous_restore_map) - set(restore_map))
    if removed_labels:
        _log_operation(
            request,
            'anonymization_labels_deleted',
            'RestoreMetadata',
            source_id,
            {'labels': removed_labels},
        )

    compare_original_html, compare_anonymized_html = highlight_changed_text(source_text, anonymized_text)

    return JsonResponse({
        'source_id': source_id,
        'prompt_pk': prompt.pk,
        'prompt_url': reverse('close_side:prompt_preview', args=[prompt.pk]),
        'prompt_json': prompt_payload,
        'restore_json': restore_payload,
        'restore_map_items': list(restore_map.items()),
        'compare_original_html': compare_original_html,
        'compare_anonymized_html': compare_anonymized_html,
    })


@require_http_methods(["GET", "POST"])
def dmz_export(request):
    saved = _owned_queryset(RestoreMetadata.objects.all(), request.user).order_by('-id')[:50]
    if request.method == 'POST':
        form = DMZExportForm(request.POST)
        if form.is_valid():
            source_id = form.cleaned_data.get('source_id')
            dmz_dir = _close_to_open_dir()

            try:
                metadata = _metadata_for_user(source_id, request.user)
                if not metadata:
                    messages.error(request, f'source_id {source_id} が見つかりません')
                    return render(request, 'anonymizer_app/dmz_export.html', {'form': form, 'saved': saved})

                payload = _sanitize_prompt_payload_for_dmz(metadata.prompt_json or {})
                payload.setdefault('metadata', {})
                payload['metadata']['source_id'] = metadata.source_id
                payload['metadata']['owner_user_id'] = metadata.owner_id
                payload['metadata']['owner_username'] = metadata.owner.get_username() if metadata.owner else ''
                payload['metadata']['sent_by'] = request.user.get_username()
                payload['metadata']['sent_at'] = timezone.now().isoformat()
                payload['metadata']['input_mode'] = payload['metadata'].get('input_mode') or (metadata.prompt_json or {}).get('metadata', {}).get('input_mode') or 'free'

                dmz_dir.mkdir(parents=True, exist_ok=True)
                filename = _prompt_json_filename(source_id)
                output_path = dmz_dir / filename
                output_path.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding='utf-8',
                )
                metadata.prompt_json = payload
                metadata.status = 'sent_to_dmz'
                metadata.save(update_fields=['prompt_json', 'status', 'updated_at'])
                Prompt.objects.filter(source_id=source_id).update(status='sent_to_dmz', updated_at=timezone.now())
                _log_operation(request, 'prompt_sent_to_dmz', 'RestoreMetadata', source_id, {'filename': filename})

                messages.success(request, f'OpenSide DMZ へ出力しました: {output_path}')
                return render(
                    request,
                    'anonymizer_app/dmz_export.html',
                    {'form': DMZExportForm(), 'uploaded_path': str(output_path), 'saved': saved},
                )
            except Exception as e:
                _log_operation(
                    request,
                    'prompt_sent_to_dmz',
                    'RestoreMetadata',
                    source_id or '',
                    {'source_id': source_id},
                    result='failure',
                    error_message=str(e),
                )
                messages.error(request, f'出力に失敗しました: {e}')
                return render(request, 'anonymizer_app/dmz_export.html', {'form': form, 'saved': saved})
    else:
        form = DMZExportForm(initial={'source_id': request.GET.get('source_id', '')})

    return render(request, 'anonymizer_app/dmz_export.html', {'form': form, 'saved': saved})


def result_history_list(request):
    context = _result_history_list_context(request)
    return render(request, 'anonymizer_app/result_history_list.html', context)


def result_history_preview(request, pk):
    context = _result_history_preview_context(request, pk)
    return render(request, 'anonymizer_app/result_history_preview.html', context)


def result_import_list(request):
    dmz_dir = _open_to_close_dir()
    try:
        files = _list_files(dmz_dir, request.user)
    except Exception as e:
        files = []
        messages.error(request, f'返却DMZファイル一覧の取得に失敗しました: {e}')

    return render(request, 'anonymizer_app/result_import_list.html', {
        'form': DMZResultImportForm(),
        'files': files,
        'dmz_path': str(dmz_dir),
    })


def result_detail(request, pk):
    result_record = get_object_or_404(_owned_queryset(RestoredResult.objects.all(), request.user), pk=pk)
    metadata = get_object_or_404(_owned_queryset(RestoreMetadata.objects.all(), request.user), source_id=result_record.source_id)
    return render(
        request,
        'anonymizer_app/restored_result.html',
        _restored_result_page_context(
            request,
            result_record,
            metadata=metadata,
            filename=result_record.imported_filename,
        ),
    )


@require_http_methods(["POST"])
def result_rerestore(request, pk):
    result_record = get_object_or_404(_owned_queryset(RestoredResult.objects.all(), request.user), pk=pk)
    metadata = get_object_or_404(_owned_queryset(RestoreMetadata.objects.all(), request.user), source_id=result_record.source_id)
    previous_restore_map = dict(metadata.restore_map or {})

    try:
        rows = _normalize_restore_label_rows(request.POST.get('restore_rows_json') or '')
    except ValueError as e:
        messages.error(request, str(e))
        return redirect('close_side:result_detail', pk=pk)

    restore_map = _augment_restore_map_with_patient_info(_restore_map_from_rows(rows), _patient_profile_for_source_id(result_record.source_id, request.user))
    updated_result_text = _apply_restore_label_renames(result_record.result_text or '', rows)
    restored_text = restore_text(updated_result_text, restore_map)
    restored_text = _prepend_patient_basic_info_to_restored_text(
        restored_text,
        result_record.template_type or metadata.template_type or '',
        _patient_profile_for_source_id(result_record.source_id, request.user),
    )

    metadata.restore_map = restore_map
    metadata.save(update_fields=['restore_map', 'updated_at'])

    result_record.result_text = updated_result_text
    result_record.restored_text = restored_text
    result_record.save(update_fields=['result_text', 'restored_text', 'updated_at'])

    renamed_labels = [
        {'from': row['old_label'], 'to': row['label']}
        for row in rows
        if row.get('old_label') and row.get('label') and row['old_label'] != row['label']
    ]
    _log_operation(
        request,
        'restored_result_rerestored',
        'RestoredResult',
        str(result_record.pk),
        {
            'source_id': result_record.source_id,
            'labels_added': sorted(label for label in restore_map if label not in previous_restore_map),
            'labels_removed': sorted(label for label in previous_restore_map if label not in restore_map),
            'labels_renamed': renamed_labels,
        },
    )
    messages.success(request, '匿名ラベルを更新して再復元しました。')
    return redirect('close_side:result_detail', pk=pk)


@require_http_methods(["POST"])
def result_import(request):
    form = DMZResultImportForm(request.POST)
    if not form.is_valid():
        messages.error(request, '取り込む返却ファイル名を指定してください。')
        return redirect('close_side:result_import_list')

    try:
        filename = _safe_filename(form.cleaned_data['filename'])
    except ValueError as e:
        _log_operation(request, 'result_imported_to_close', 'RestoredResult', '', result='failure', error_message=str(e))
        messages.error(request, str(e))
        return redirect('close_side:result_import_list')

    result_path = _open_to_close_dir() / filename
    if not result_path.exists() or not result_path.is_file():
        _log_operation(
            request,
            'result_imported_to_close',
            'RestoredResult',
            filename,
            {'filename': filename},
            result='failure',
            error_message='返却ファイルが見つかりません',
        )
        messages.error(request, f'返却ファイルが見つかりません: {filename}')
        return redirect('close_side:result_import_list')

    try:
        result_payload = json.loads(result_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        _log_operation(
            request,
            'result_imported_to_close',
            'RestoredResult',
            filename,
            {'filename': filename},
            result='failure',
            error_message='返却ファイルをJSONとして解析できません',
        )
        messages.error(request, '返却ファイルをJSONとして解析できません。')
        return redirect('close_side:result_import_list')

    source_id = result_payload.get('source_id') or result_payload.get('metadata', {}).get('source_id') or ''
    result_text_value = result_payload.get('result_text') or ''
    if not source_id or not result_text_value:
        _log_operation(
            request,
            'result_imported_to_close',
            'RestoredResult',
            source_id or filename,
            {'filename': filename, 'source_id': source_id},
            result='failure',
            error_message='返却JSONには source_id と result_text が必要です',
        )
        messages.error(request, '返却JSONには source_id と result_text が必要です。')
        return redirect('close_side:result_import_list')
    if not _payload_visible_to_user(result_payload, request.user):
        _log_operation(
            request,
            'result_imported_to_close',
            'RestoredResult',
            source_id,
            {'filename': filename, 'source_id': source_id},
            result='failure',
            error_message='返却ファイルを取り込む権限がありません',
        )
        messages.error(request, 'この返却ファイルを取り込む権限がありません。')
        return redirect('close_side:result_import_list')

    metadata = _metadata_for_user(source_id, request.user)
    if metadata is None:
        _log_operation(
            request,
            'result_imported_to_close',
            'RestoredResult',
            source_id,
            {'filename': filename, 'source_id': source_id},
            result='failure',
            error_message='対応する復元メタデータが見つかりません',
        )
        messages.error(request, f'source_id {source_id} に対応する復元メタデータが見つかりません。')
        return redirect('close_side:result_import_list')

    patient_profile = _patient_profile_for_source_id(source_id, request.user)
    restore_map = _augment_restore_map_with_patient_info(metadata.restore_map or {}, patient_profile)
    template_type = result_payload.get('template_type') or metadata.template_type
    restored_text = restore_text(result_text_value, restore_map)
    restored_text = _prepend_patient_basic_info_to_restored_text(
        restored_text,
        template_type,
        patient_profile,
    )
    reviewer = result_payload.get('metadata', {}).get('reviewer') or ''
    input_mode = result_payload.get('metadata', {}).get('input_mode') or ''
    result_record = RestoredResult.objects.create(
        source_id=source_id,
        result_id=result_payload.get('id') or '',
        template_type=template_type,
        result_text=result_text_value,
        restored_text=restored_text,
        result_json=result_payload,
        imported_filename=filename,
        reviewer=reviewer,
        owner=metadata.owner or request.user,
        status='imported',
    )
    metadata.restore_map = restore_map
    metadata.status = 'imported_to_close'
    metadata.save(update_fields=['restore_map', 'status', 'updated_at'])
    try:
        result_path.unlink()
    except OSError as e:
        messages.warning(request, f'DMZ返却ファイルの削除に失敗しました: {e}')
    _log_operation(request, 'result_imported_to_close', 'RestoredResult', str(result_record.pk), {
        'filename': filename,
        'source_id': source_id,
    })

    messages.success(request, f'返却JSONを取り込み、復元しました: {filename}')
    return redirect('close_side:result_detail', pk=result_record.pk)


@require_http_methods(["POST"])
def transcribe_audio(request):
    audio_file = request.FILES.get('audio_file') or request.FILES.get('file')
    if audio_file is None:
        return JsonResponse({'error': '音声ファイルが必要です。'}, status=400)

    template_type = str(request.POST.get('template_type') or '').strip()
    transcript_source = str(request.POST.get('transcript_source') or '').strip() or 'uploaded_audio'

    try:
        transcription = transcribe_audio_file(audio_file, template_type=template_type)
    except TranscriptionConfigurationError as e:
        return JsonResponse({'error': str(e)}, status=503)
    except TranscriptionRequestError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except TranscriptionServiceError as e:
        return JsonResponse({'error': str(e)}, status=502)

    return JsonResponse({
        'text': transcription['text'],
        'model': transcription['model'],
        'transcript_source': transcript_source,
    })


@require_http_methods(["POST"])
def result_delete(request, pk):
    result = get_object_or_404(_owned_queryset(RestoredResult.objects.all(), request.user), pk=pk)
    target_id = result.result_id or result.source_id or str(result.pk)
    result.delete()
    _log_operation(request, 'restored_result_deleted', 'RestoredResult', target_id)
    messages.success(request, '取り込み済み生成文章を削除しました。')
    redirect_url = reverse('close_side:result_history_list')
    history_query = request.GET.get('q', '').strip()
    if history_query:
        redirect_url = f'{redirect_url}?{urlencode({"q": history_query})}'
    return redirect(redirect_url)


def patient_list(request):
    query_params = request.GET.copy()
    sort_choices = {'patient_id', 'kana', 'sex', 'birth_date'}
    sort_value = str(query_params.get('sort') or 'patient_id').strip() or 'patient_id'
    if sort_value not in sort_choices:
        sort_value = 'patient_id'
    query_params['sort'] = sort_value
    form = PatientSearchForm(query_params)

    patient_id_query = str(request.GET.get('patient_id') or '').strip()
    kana_query = re.sub(r'[\s　]+', '', str(request.GET.get('kana') or '').strip())
    sex_query = str(request.GET.get('sex') or '').strip()
    birth_date_query = _parse_patient_birth_date(request.GET.get('birth_date'))
    diagnosis_query = str(request.GET.get('primary_diagnosis') or '').strip()

    queryset = Patient.objects.all()
    if patient_id_query:
        queryset = queryset.filter(patient_id__icontains=patient_id_query)
    if kana_query:
        queryset = queryset.annotate(kana_full_name_search=Concat('kana_surname', 'kana_given_name')).filter(
            Q(kana_full_name_search__icontains=kana_query)
            | Q(kana_surname__icontains=kana_query)
            | Q(kana_given_name__icontains=kana_query)
        )
    if sex_query and sex_query in {choice[0] for choice in Patient.SEX_CHOICES}:
        queryset = queryset.filter(sex=sex_query)
    if birth_date_query:
        queryset = queryset.filter(birth_date=birth_date_query)
    if diagnosis_query:
        queryset = queryset.filter(primary_diagnosis__icontains=diagnosis_query)

    patients = list(_patient_sort_queryset(queryset, sort_value))

    return render(request, 'anonymizer_app/patient_list.html', {
        'form': form,
        'patients': patients,
        'sort_value': sort_value,
        'query_count': len(patients),
        'has_filters': any([
            patient_id_query,
            kana_query,
            sex_query,
            birth_date_query,
            diagnosis_query,
        ]),
    })


@require_http_methods(["GET", "POST"])
def patient_create(request):
    if request.method == 'POST':
        form = PatientForm(request.POST)
        if form.is_valid():
            patient = form.save()
            _log_operation(request, 'patient_created', 'Patient', patient.patient_id)
            messages.success(request, f'患者マスタを追加しました: {patient.patient_id}')
            return redirect('close_side:patient_list')
    else:
        form = PatientForm()

    return render(request, 'anonymizer_app/patient_form.html', {
        'form': form,
        'create': True,
        'back_url': reverse('close_side:patient_list'),
    })


@require_http_methods(["GET", "POST"])
def patient_edit(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    if request.method == 'POST':
        form = PatientForm(request.POST, instance=patient)
        if form.is_valid():
            patient = form.save()
            _log_operation(request, 'patient_updated', 'Patient', patient.patient_id)
            messages.success(request, f'患者マスタを更新しました: {patient.patient_id}')
            return redirect('close_side:patient_list')
    else:
        form = PatientForm(instance=patient)

    return render(request, 'anonymizer_app/patient_form.html', {
        'form': form,
        'create': False,
        'patient': patient,
        'back_url': reverse('close_side:patient_list'),
    })


@require_http_methods(["POST"])
def patient_delete(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    target_id = patient.patient_id
    patient.delete()
    _log_operation(request, 'patient_deleted', 'Patient', target_id)
    messages.success(request, f'患者マスタを削除しました: {target_id}')
    return redirect('close_side:patient_list')


@require_http_methods(["GET", "POST"])
def patient_import(request):
    if request.method == 'POST':
        form = PatientImportForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = form.cleaned_data['csv_file']
            try:
                import_summary = _import_patient_csv(csv_file)
                _log_operation(
                    request,
                    'patient_imported',
                    'Patient',
                    getattr(csv_file, 'name', ''),
                    import_summary,
                )
                messages.success(
                    request,
                    (
                        f"患者CSVを取り込みました。"
                        f"新規 {import_summary['created']} 件、"
                        f"更新 {import_summary['updated']} 件、"
                        f"スキップ {import_summary['skipped']} 件。"
                    ),
                )
                return redirect('close_side:patient_list')
            except Exception as e:
                form.add_error('csv_file', f'CSV取込に失敗しました: {e}')
                _log_operation(
                    request,
                    'patient_imported',
                    'Patient',
                    getattr(csv_file, 'name', ''),
                    import_summary if 'import_summary' in locals() else None,
                    result='failure',
                    error_message=str(e),
                )
    else:
        form = PatientImportForm()

    return render(request, 'anonymizer_app/patient_import.html', {
        'form': form,
        'back_url': reverse('close_side:patient_list'),
    })


@require_http_methods(["GET"])
def patient_lookup(request, patient_id):
    patient = _patient_for_patient_id(patient_id)
    if patient is None:
        return JsonResponse({
            'found': False,
            'patient_id': str(patient_id or '').strip(),
            'error': f'患者ID {str(patient_id or "").strip()} が見つかりません。',
        }, status=404)

    return JsonResponse({
        'found': True,
        'patient': _patient_payload(patient),
    })


def staff_list(request):
    query_params = request.GET.copy()
    sort_choices = {'staff_id', 'kana', 'occupation_label', 'position_label', 'is_active', 'updated_at'}
    sort_value = str(query_params.get('sort') or 'staff_id').strip() or 'staff_id'
    if sort_value not in sort_choices:
        sort_value = 'staff_id'
    query_params['sort'] = sort_value
    form = StaffSearchForm(query_params)

    staff_id_query = str(request.GET.get('staff_id') or '').strip()
    kana_query = re.sub(r'[\s　]+', '', str(request.GET.get('kana') or '').strip())
    occupation_label_query = str(request.GET.get('occupation_label') or '').strip()
    position_label_query = str(request.GET.get('position_label') or '').strip()
    is_active_query = str(request.GET.get('is_active') or '').strip()

    queryset = Staff.objects.all()
    if staff_id_query:
        queryset = queryset.filter(staff_id__icontains=staff_id_query)
    if kana_query:
        queryset = queryset.annotate(kana_full_name_search=Concat('kana_surname', 'kana_given_name')).filter(
            Q(kana_full_name_search__icontains=kana_query)
            | Q(kana_surname__icontains=kana_query)
            | Q(kana_given_name__icontains=kana_query)
        )
    if occupation_label_query:
        queryset = queryset.filter(occupation_label__icontains=occupation_label_query)
    if position_label_query:
        queryset = queryset.filter(position_label__icontains=position_label_query)
    if is_active_query in {'1', '0'}:
        queryset = queryset.filter(is_active=is_active_query == '1')

    staff_members = list(_staff_sort_queryset(queryset, sort_value))

    return render(request, 'anonymizer_app/staff_list.html', {
        'form': form,
        'staff_members': staff_members,
        'sort_value': sort_value,
        'query_count': len(staff_members),
        'has_filters': any([
            staff_id_query,
            kana_query,
            occupation_label_query,
            position_label_query,
            is_active_query in {'1', '0'},
        ]),
    })


@require_http_methods(["GET", "POST"])
def staff_create(request):
    if request.method == 'POST':
        form = StaffForm(request.POST)
        if form.is_valid():
            staff = form.save()
            _log_operation(request, 'staff_created', 'Staff', staff.staff_id)
            messages.success(request, f'職員マスタを追加しました: {staff.staff_id}')
            return redirect('close_side:staff_list')
    else:
        form = StaffForm()

    return render(request, 'anonymizer_app/staff_form.html', {
        'form': form,
        'create': True,
        'back_url': reverse('close_side:staff_list'),
    })


@require_http_methods(["GET", "POST"])
def staff_edit(request, pk):
    staff = get_object_or_404(Staff, pk=pk)
    if request.method == 'POST':
        form = StaffForm(request.POST, instance=staff)
        if form.is_valid():
            staff = form.save()
            _log_operation(request, 'staff_updated', 'Staff', staff.staff_id)
            messages.success(request, f'職員マスタを更新しました: {staff.staff_id}')
            return redirect('close_side:staff_list')
    else:
        form = StaffForm(instance=staff)

    return render(request, 'anonymizer_app/staff_form.html', {
        'form': form,
        'create': False,
        'staff': staff,
        'back_url': reverse('close_side:staff_list'),
    })


@require_http_methods(["POST"])
def staff_delete(request, pk):
    staff = get_object_or_404(Staff, pk=pk)
    target_id = staff.staff_id
    staff.delete()
    _log_operation(request, 'staff_deleted', 'Staff', target_id)
    messages.success(request, f'職員マスタを削除しました: {target_id}')
    return redirect('close_side:staff_list')


@require_http_methods(["GET", "POST"])
def staff_import(request):
    if request.method == 'POST':
        form = StaffImportForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = form.cleaned_data['csv_file']
            try:
                import_summary = _import_staff_csv(csv_file)
                _log_operation(
                    request,
                    'staff_imported',
                    'Staff',
                    getattr(csv_file, 'name', ''),
                    import_summary,
                )
                messages.success(
                    request,
                    (
                        f"職員CSVを取り込みました。"
                        f"新規 {import_summary['created']} 件、"
                        f"更新 {import_summary['updated']} 件、"
                        f"スキップ {import_summary['skipped']} 件。"
                    ),
                )
                return redirect('close_side:staff_list')
            except Exception as e:
                form.add_error('csv_file', f'CSV取込に失敗しました: {e}')
                _log_operation(
                    request,
                    'staff_imported',
                    'Staff',
                    getattr(csv_file, 'name', ''),
                    import_summary if 'import_summary' in locals() else None,
                    result='failure',
                    error_message=str(e),
                )
    else:
        form = StaffImportForm()

    return render(request, 'anonymizer_app/staff_import.html', {
        'form': form,
        'back_url': reverse('close_side:staff_list'),
    })


def _linked_person_form_post_data(post_data, default_relation_kind: str | None = None):
    if default_relation_kind is None:
        return post_data

    data = post_data.copy()
    if not str(data.get('relation_kind') or '').strip():
        data['relation_kind'] = default_relation_kind
    return data


def _linked_person_list_view(
    request,
    *,
    page_title: str,
    page_subtitle: str,
    relation_kind_filter: str | None = None,
    create_url_name: str = 'close_side:linked_person_create',
    import_url_name: str = 'close_side:linked_person_import',
    edit_url_name: str = 'close_side:linked_person_edit',
    delete_url_name: str = 'close_side:linked_person_delete',
    clear_url_name: str = 'close_side:linked_person_list',
):
    query_params = request.GET.copy()
    sort_choices = {'linked_person_code', 'patient_id', 'branch_no', 'relation_kind', 'kana', 'relationship_label', 'is_active', 'updated_at'}
    sort_value = str(query_params.get('sort') or 'patient_id').strip() or 'patient_id'
    if sort_value not in sort_choices:
        sort_value = 'patient_id'
    query_params['sort'] = sort_value
    if relation_kind_filter:
        query_params['relation_kind'] = relation_kind_filter
    form = PatientLinkedPersonSearchForm(query_params)
    if relation_kind_filter:
        form.fields['relation_kind'].disabled = True

    linked_person_code_query = str(request.GET.get('linked_person_code') or '').strip()
    patient_id_query = str(request.GET.get('patient_id') or '').strip()
    branch_no_query = str(request.GET.get('branch_no') or '').strip()
    relation_kind_query = relation_kind_filter or str(request.GET.get('relation_kind') or '').strip()
    kana_query = re.sub(r'[\s　]+', '', str(request.GET.get('kana') or '').strip())
    relationship_label_query = str(request.GET.get('relationship_label') or '').strip()
    is_active_query = str(request.GET.get('is_active') or '').strip()

    queryset = PatientLinkedPerson.objects.all()
    if relation_kind_filter:
        queryset = queryset.filter(relation_kind=relation_kind_filter)
    elif relation_kind_query:
        normalized_relation_kind = _normalize_relation_kind_value(relation_kind_query)
        if normalized_relation_kind:
            queryset = queryset.filter(relation_kind=normalized_relation_kind)
    relation_kind_filter_label = '家族' if relation_kind_filter == 'family' else '後見人' if relation_kind_filter == 'guardian' else ''
    if linked_person_code_query:
        queryset = queryset.filter(linked_person_code__icontains=linked_person_code_query)
    if patient_id_query:
        queryset = queryset.filter(patient_id__icontains=patient_id_query)
    branch_no_value = _normalize_branch_no_value(branch_no_query)
    if branch_no_value is not None:
        queryset = queryset.filter(branch_no=branch_no_value)
    if kana_query:
        queryset = queryset.annotate(kana_full_name_search=Concat('kana_surname', 'kana_given_name')).filter(
            Q(kana_full_name_search__icontains=kana_query)
            | Q(kana_surname__icontains=kana_query)
            | Q(kana_given_name__icontains=kana_query)
        )
    if relationship_label_query:
        queryset = queryset.filter(relationship_label__icontains=relationship_label_query)
    if is_active_query in {'1', '0'}:
        queryset = queryset.filter(is_active=is_active_query == '1')

    linked_persons = list(_patient_linked_person_sort_queryset(queryset, sort_value, 'branch_no'))
    clear_url = reverse(clear_url_name)

    return render(request, 'anonymizer_app/linked_person_list.html', {
        'form': form,
        'linked_persons': linked_persons,
        'sort_value': sort_value,
        'query_count': len(linked_persons),
        'has_filters': any([
            linked_person_code_query,
            patient_id_query,
            branch_no_query,
            relation_kind_query if not relation_kind_filter else False,
            kana_query,
            relationship_label_query,
            is_active_query in {'1', '0'},
        ]),
        'page_title': page_title,
        'page_subtitle': page_subtitle,
        'clear_url': clear_url,
        'create_url': reverse(create_url_name),
        'import_url': reverse(import_url_name),
        'list_title': page_title,
        'entity_label': relation_kind_filter_label or '患者関連者',
        'edit_url_name': edit_url_name,
        'delete_url_name': delete_url_name,
        'relation_kind_filter': relation_kind_filter or '',
        'relation_kind_filter_label': relation_kind_filter_label,
    })


def _linked_person_form_view(
    request,
    *,
    create: bool,
    back_url_name: str,
    page_title: str,
    page_subtitle: str,
    relation_kind_filter: str | None = None,
    instance: PatientLinkedPerson | None = None,
    success_action: str,
):
    back_url = reverse(back_url_name)
    relation_kind_filter_label = '家族' if relation_kind_filter == 'family' else '後見人' if relation_kind_filter == 'guardian' else ''
    if request.method == 'POST':
        form_data = _linked_person_form_post_data(request.POST, relation_kind_filter)
        form = PatientLinkedPersonForm(form_data, instance=instance)
        if relation_kind_filter:
            form.fields['relation_kind'].disabled = True
            form.initial['relation_kind'] = relation_kind_filter
        if form.is_valid():
            linked_person = form.save()
            target_label = linked_person.linked_person_display_label
            _log_operation(request, success_action, 'PatientLinkedPerson', target_label)
            messages.success(
                request,
                f'{linked_person.relation_kind_label}マスタを{"追加" if create else "更新"}しました: {target_label}',
            )
            return redirect(back_url_name)
    else:
        initial = {}
        if relation_kind_filter:
            initial['relation_kind'] = relation_kind_filter
        form = PatientLinkedPersonForm(instance=instance, initial=initial)
        if relation_kind_filter:
            form.fields['relation_kind'].disabled = True

    return render(request, 'anonymizer_app/linked_person_form.html', {
        'form': form,
        'create': create,
        'page_title': page_title,
        'page_subtitle': page_subtitle,
        'back_url': back_url,
        'entity_label': relation_kind_filter_label or '患者関連者',
        'relation_kind_filter_label': relation_kind_filter_label,
    })


def _linked_person_delete_view(
    request,
    *,
    pk: int,
    back_url_name: str,
    success_action: str,
    relation_kind_filter: str | None = None,
):
    queryset = PatientLinkedPerson.objects.all()
    if relation_kind_filter:
        queryset = queryset.filter(relation_kind=relation_kind_filter)
    linked_person = get_object_or_404(queryset, pk=pk)
    target_id = linked_person.linked_person_display_label
    linked_person.delete()
    _log_operation(request, success_action, 'PatientLinkedPerson', target_id)
    messages.success(request, f'{linked_person.relation_kind_label}マスタを削除しました: {target_id}')
    return redirect(back_url_name)


def _linked_person_import_view(
    request,
    *,
    back_url_name: str,
    page_title: str,
    page_subtitle: str,
    record_label: str,
    default_relation_kind: str | None,
    import_action: str,
):
    if request.method == 'POST':
        form = PatientLinkedPersonImportForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = form.cleaned_data['csv_file']
            try:
                import_summary = _import_patient_linked_csv(
                    csv_file,
                    model_cls=PatientLinkedPerson,
                    header_aliases=LINKED_PERSON_CSV_HEADER_ALIASES,
                    record_label=record_label,
                    header_example='患者ID,枝番,種別,属性,姓,名,ふりかな姓,ふりかな名,有効',
                    default_relation_kind=default_relation_kind,
                )
                _log_operation(
                    request,
                    import_action,
                    'PatientLinkedPerson',
                    getattr(csv_file, 'name', ''),
                    import_summary,
                )
                messages.success(
                    request,
                    (
                        f"{record_label}CSVを取り込みました。"
                        f"新規 {import_summary['created']} 件、"
                        f"更新 {import_summary['updated']} 件、"
                        f"スキップ {import_summary['skipped']} 件。"
                    ),
                )
                return redirect(back_url_name)
            except Exception as e:
                form.add_error('csv_file', f'CSV取込に失敗しました: {e}')
                _log_operation(
                    request,
                    import_action,
                    'PatientLinkedPerson',
                    getattr(csv_file, 'name', ''),
                    import_summary if 'import_summary' in locals() else None,
                    result='failure',
                    error_message=str(e),
                )
    else:
        form = PatientLinkedPersonImportForm()

    return render(request, 'anonymizer_app/linked_person_import.html', {
        'form': form,
        'page_title': page_title,
        'page_subtitle': page_subtitle,
        'back_url': reverse(back_url_name),
        'entity_label': record_label,
        'default_relation_kind_label': '家族' if default_relation_kind == 'family' else '後見人' if default_relation_kind == 'guardian' else '',
    })


def linked_person_list(request):
    return _linked_person_list_view(
        request,
        page_title='患者関連者管理',
        page_subtitle='患者に紐づく家族・後見人マスターの検索、追加、編集、削除、CSV取込を行います。個別コードは自動採番、枝番は患者内の並び順として残します。',
    )


@require_http_methods(["GET", "POST"])
def linked_person_create(request):
    return _linked_person_form_view(
        request,
        create=True,
        back_url_name='close_side:linked_person_list',
        page_title='患者関連者マスタ追加',
        page_subtitle='患者に紐づく家族・後見人マスターを追加します。個別コードは保存時に自動採番されます。',
        relation_kind_filter=None,
        instance=None,
        success_action='linked_person_created',
    )


@require_http_methods(["GET", "POST"])
def linked_person_edit(request, pk):
    linked_person = get_object_or_404(PatientLinkedPerson, pk=pk)
    return _linked_person_form_view(
        request,
        create=False,
        back_url_name='close_side:linked_person_list',
        page_title='患者関連者マスタ編集',
        page_subtitle='患者に紐づく家族・後見人マスターを編集します。個別コードは変更しません。',
        relation_kind_filter=None,
        instance=linked_person,
        success_action='linked_person_updated',
    )


@require_http_methods(["POST"])
def linked_person_delete(request, pk):
    return _linked_person_delete_view(
        request,
        pk=pk,
        back_url_name='close_side:linked_person_list',
        success_action='linked_person_deleted',
    )


@require_http_methods(["GET", "POST"])
def linked_person_import(request):
    return _linked_person_import_view(
        request,
        back_url_name='close_side:linked_person_list',
        page_title='患者関連者CSV取込',
        page_subtitle='患者に紐づく家族・後見人マスターをCSVから一括登録・更新します。個別コードは自動採番されるため、CSVでは患者IDと枝番を使います。',
        record_label='患者関連者',
        default_relation_kind=None,
        import_action='linked_person_imported',
    )


def family_list(request):
    return _linked_person_list_view(
        request,
        page_title='家族管理',
        page_subtitle='患者に紐づく家族マスターの検索、追加、編集、削除、CSV取込を行います。',
        relation_kind_filter='family',
        create_url_name='close_side:family_create',
        import_url_name='close_side:family_import',
        edit_url_name='close_side:family_edit',
        delete_url_name='close_side:family_delete',
        clear_url_name='close_side:family_list',
    )


@require_http_methods(["GET", "POST"])
def family_create(request):
    return _linked_person_form_view(
        request,
        create=True,
        back_url_name='close_side:family_list',
        page_title='家族マスタ追加',
        page_subtitle='患者に紐づく家族マスターを追加します。',
        relation_kind_filter='family',
        instance=None,
        success_action='family_created',
    )


@require_http_methods(["GET", "POST"])
def family_edit(request, pk):
    linked_person = get_object_or_404(PatientLinkedPerson, pk=pk, relation_kind='family')
    return _linked_person_form_view(
        request,
        create=False,
        back_url_name='close_side:family_list',
        page_title='家族マスタ編集',
        page_subtitle='患者に紐づく家族マスターを編集します。',
        relation_kind_filter='family',
        instance=linked_person,
        success_action='family_updated',
    )


@require_http_methods(["POST"])
def family_delete(request, pk):
    return _linked_person_delete_view(
        request,
        pk=pk,
        back_url_name='close_side:family_list',
        success_action='family_deleted',
        relation_kind_filter='family',
    )


@require_http_methods(["GET", "POST"])
def family_import(request):
    return _linked_person_import_view(
        request,
        back_url_name='close_side:family_list',
        page_title='家族CSV取込',
        page_subtitle='患者に紐づく家族マスターをCSVから一括登録・更新します。',
        record_label='家族',
        default_relation_kind='family',
        import_action='family_imported',
    )


def guardian_list(request):
    return _linked_person_list_view(
        request,
        page_title='後見人管理',
        page_subtitle='患者に紐づく後見人マスターの検索、追加、編集、削除、CSV取込を行います。',
        relation_kind_filter='guardian',
        create_url_name='close_side:guardian_create',
        import_url_name='close_side:guardian_import',
        edit_url_name='close_side:guardian_edit',
        delete_url_name='close_side:guardian_delete',
        clear_url_name='close_side:guardian_list',
    )


@require_http_methods(["GET", "POST"])
def guardian_create(request):
    return _linked_person_form_view(
        request,
        create=True,
        back_url_name='close_side:guardian_list',
        page_title='後見人マスタ追加',
        page_subtitle='患者に紐づく後見人マスターを追加します。',
        relation_kind_filter='guardian',
        instance=None,
        success_action='guardian_created',
    )


@require_http_methods(["GET", "POST"])
def guardian_edit(request, pk):
    linked_person = get_object_or_404(PatientLinkedPerson, pk=pk, relation_kind='guardian')
    return _linked_person_form_view(
        request,
        create=False,
        back_url_name='close_side:guardian_list',
        page_title='後見人マスタ編集',
        page_subtitle='患者に紐づく後見人マスターを編集します。',
        relation_kind_filter='guardian',
        instance=linked_person,
        success_action='guardian_updated',
    )


@require_http_methods(["POST"])
def guardian_delete(request, pk):
    return _linked_person_delete_view(
        request,
        pk=pk,
        back_url_name='close_side:guardian_list',
        success_action='guardian_deleted',
        relation_kind_filter='guardian',
    )


@require_http_methods(["GET", "POST"])
def guardian_import(request):
    return _linked_person_import_view(
        request,
        back_url_name='close_side:guardian_list',
        page_title='後見人CSV取込',
        page_subtitle='患者に紐づく後見人マスターをCSVから一括登録・更新します。',
        record_label='後見人',
        default_relation_kind='guardian',
        import_action='guardian_imported',
    )


def prompts_list(request):
    prompts = _owned_queryset(Prompt.objects.all(), request.user).order_by('-updated_at')
    return render(request, 'anonymizer_app/prompts_list.html', {'prompts': prompts})


def prompt_preview(request, pk):
    prompt = get_object_or_404(_owned_queryset(Prompt.objects.all(), request.user), pk=pk)
    return render(request, 'anonymizer_app/prompt_preview.html', {'prompt': prompt})


def prompt_create(request):
    back_url = reverse('close_side:prompts_list')
    if request.method == 'POST':
        form = PromptForm(request.POST)
        if form.is_valid():
            prompt = Prompt.objects.create(
                name=form.cleaned_data['name'],
                content=form.cleaned_data['content'],
                owner=request.user,
            )
            _log_operation(request, 'prompt_created_manually', 'Prompt', str(prompt.pk))
            return redirect('close_side:prompt_preview', pk=prompt.pk)
    else:
        form = PromptForm()
    return render(request, 'anonymizer_app/prompt_form.html', {
        'form': form,
        'create': True,
        'back_url': back_url,
        'back_label': '一覧へ戻る',
    })


def prompt_edit(request, pk):
    prompt = get_object_or_404(_owned_queryset(Prompt.objects.all(), request.user), pk=pk)
    back_url = reverse('close_side:prompt_preview', args=[prompt.pk])
    if request.method == 'POST':
        form = PromptForm(request.POST)
        if form.is_valid():
            prompt.name = form.cleaned_data['name']
            prompt.content = form.cleaned_data['content']
            prompt.save()
            _log_operation(request, 'prompt_updated', 'Prompt', str(prompt.pk))
            return redirect('close_side:prompt_preview', pk=prompt.pk)
    else:
        form = PromptForm(initial={'name': prompt.name, 'content': prompt.content})
    return render(request, 'anonymizer_app/prompt_form.html', {
        'form': form,
        'create': False,
        'prompt': prompt,
        'back_url': back_url,
        'back_label': 'プレビューへ戻る',
    })


@require_http_methods(["POST"])
def prompt_delete(request, pk):
    prompt = get_object_or_404(_owned_queryset(Prompt.objects.all(), request.user), pk=pk)
    target_id = prompt.source_id or str(prompt.pk)
    prompt.delete()
    _log_operation(request, 'prompt_deleted', 'Prompt', target_id)
    messages.success(request, 'プロンプトを削除しました。')
    return redirect('close_side:prompts_list')


@require_http_methods(["POST"])
def prompt_send_to_dmz(request, pk):
    prompt = get_object_or_404(_owned_queryset(Prompt.objects.all(), request.user), pk=pk)
    source_id = prompt.source_id
    metadata = _metadata_for_user(source_id, request.user) if source_id else None

    if metadata is None:
        source_id = f'prompt_manual_{prompt.pk}_{uuid.uuid4().hex[:8]}'
        payload = build_prompt_payload('手動プロンプト', {'text': prompt.content}, source_id, title=prompt.name)
        payload['metadata']['created_at'] = None
        payload['metadata']['owner_user_id'] = request.user.id
        payload['metadata']['owner_username'] = request.user.get_username()
        metadata = RestoreMetadata.objects.create(
            source_id=source_id,
            template_type='手動プロンプト',
            restore_map={},
            prompt_json=payload,
            owner=request.user,
            status='draft',
        )
        prompt.source_id = source_id

    dmz_dir = _close_to_open_dir()
    dmz_dir.mkdir(parents=True, exist_ok=True)
    payload = metadata.prompt_json or build_prompt_payload(metadata.template_type, {'text': prompt.content}, source_id)
    owner = metadata.owner or prompt.owner or request.user
    payload = _sanitize_prompt_payload_for_dmz(payload)
    payload.setdefault('metadata', {})
    payload['metadata']['source_id'] = source_id
    payload['metadata']['owner_user_id'] = owner.id
    payload['metadata']['owner_username'] = owner.get_username()
    payload['metadata']['sent_by'] = request.user.get_username()
    payload['metadata']['sent_at'] = timezone.now().isoformat()
    payload['metadata']['input_mode'] = payload['metadata'].get('input_mode') or (metadata.prompt_json or {}).get('metadata', {}).get('input_mode') or 'free'
    output_filename = _prompt_json_filename(source_id)
    output_path = dmz_dir / output_filename
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    metadata.prompt_json = payload
    metadata.status = 'sent_to_dmz'
    metadata.save(update_fields=['prompt_json', 'status', 'updated_at'])
    prompt.status = 'sent_to_dmz'
    prompt.save(update_fields=['source_id', 'status', 'updated_at'])
    _log_operation(request, 'prompt_sent_to_dmz', 'Prompt', str(prompt.pk), {'filename': output_filename})
    messages.success(request, f'DMZへ送信しました: {output_filename}')
    return redirect('close_side:prompt_preview', pk=prompt.pk)


def templates_list(request):
    sync_templates_to_db()
    templates = list(
        _managed_template_queryset().order_by('sort_order', 'template_type', 'name', 'id')
    )
    return render(request, 'anonymizer_app/templates_list.html', {'templates': templates})


def template_create(request):
    if request.method == 'POST':
        form = TemplateForm(request.POST)
        if form.is_valid():
            basic = form.cleaned_data.get('basic_content') or ''
            additional = form.cleaned_data.get('additional_content') or ''
            source = write_template_source(
                source_filename=None,
                template_type=form.cleaned_data['template_type'],
                name=form.cleaned_data['name'],
                basic_content=basic,
                additional_content=additional,
            )
            sync_templates_to_db()
            Template.objects.filter(source_filename=source.source_filename).update(
                description=form.cleaned_data.get('description') or '',
                created_by=request.user,
            )
            _log_operation(request, 'template_created', 'Template', source.source_filename)
            messages.success(request, f'txtテンプレートを保存しました: {source.source_filename}')
            return redirect('close_side:templates_list')
    else:
        form = TemplateForm(initial={'basic_content': load_basic_template()})
    return render(request, 'anonymizer_app/template_form.html', {'form': form, 'create': True})


def template_edit(request, pk):
    sync_templates_to_db()
    tpl = get_object_or_404(Template, pk=pk)
    if request.method == 'POST':
        form = TemplateForm(request.POST)
        if form.is_valid():
            basic = form.cleaned_data.get('basic_content') or ''
            additional = form.cleaned_data.get('additional_content') or ''
            source = write_template_source(
                source_filename=tpl.source_filename or None,
                template_type=form.cleaned_data['template_type'],
                name=form.cleaned_data['name'],
                basic_content=basic,
                additional_content=additional,
            )
            sync_templates_to_db()
            Template.objects.filter(source_filename=source.source_filename).update(
                description=form.cleaned_data.get('description') or '',
                created_by=tpl.created_by or request.user,
            )
            _log_operation(request, 'template_updated', 'Template', source.source_filename)
            messages.success(request, f'txtテンプレートを更新しました: {source.source_filename}')
            return redirect('close_side:templates_list')
    else:
        source = None
        if tpl.source_filename:
            source = get_template_source_by_filename(tpl.source_filename)
        if source is None:
            source = get_template_source_by_name(tpl.name)
        form = TemplateForm(initial={
            'template_type': source.template_type if source else tpl.template_type,
            'name': source.name if source else tpl.name,
            'description': tpl.description,
            'basic_content': source.basic_content if source else (tpl.basic_content or tpl.content),
            'additional_content': source.additional_content if source else tpl.additional_content,
        })
    return render(request, 'anonymizer_app/template_form.html', {'form': form, 'create': False, 'template': tpl})


@require_http_methods(["POST"])
def template_reorder(request):
    sync_templates_to_db()
    templates = list(
        _managed_template_queryset().order_by('sort_order', 'template_type', 'name', 'id')
    )

    submitted_orders: dict[int, int] = {}
    for template in templates:
        raw_value = str(request.POST.get(f'sort_order__{template.pk}') or '').strip()
        try:
            submitted_order = int(raw_value)
        except Exception:
            submitted_order = template.sort_order or 0
        if submitted_order < 1:
            submitted_order = template.sort_order or 0
        submitted_orders[template.pk] = submitted_order

    ordered_templates = sorted(
        templates,
        key=lambda template: (
            submitted_orders.get(template.pk, template.sort_order or 0),
            template.sort_order,
            template.pk,
        ),
    )
    _normalize_template_sort_order(ordered_templates)
    messages.success(request, 'テンプレートの表示順を更新しました。')
    return redirect('close_side:templates_list')


@require_http_methods(["POST"])
def template_toggle_active(request, pk):
    sync_templates_to_db()
    tpl = get_object_or_404(Template, pk=pk)
    tpl.is_active = not tpl.is_active
    tpl.save(update_fields=['is_active', 'updated_at'])
    messages.success(request, f'テンプレートを{"有効" if tpl.is_active else "無効"}にしました。')
    return redirect('close_side:templates_list')


def template_input_defaults_edit(request, template_type):
    canonical_template_type = TEMPLATE_INPUT_SCHEMA_ALIASES.get(template_type, template_type)
    if canonical_template_type not in TEMPLATE_INPUT_SCHEMAS:
        return render(request, 'anonymizer_app/error.html', {'message': 'テンプレートが見つかりません'}, status=404)

    schema = get_template_input_schema(canonical_template_type)
    field_keys = [str(field['key']) for field in schema]
    existing_rows = {
        row.field_key: row
        for row in TemplateInputDefault.objects.filter(template_type=canonical_template_type)
    }
    initial = {}
    for field in schema:
        field_key = str(field['key'])
        row = existing_rows.get(field_key)
        initial[f'default__{field_key}'] = str(row.default_text if row else field.get('default') or '')
        if row is not None and row.required_override is not None:
            initial[f'required__{field_key}'] = 'true' if row.required_override else 'false'
        else:
            initial[f'required__{field_key}'] = ''

    if request.method == 'POST':
        form = TemplateInputDefaultsForm(request.POST, template_type=canonical_template_type)
        if form.is_valid():
            for field in schema:
                field_key = str(field['key'])
                required_choice = str(form.cleaned_data.get(f'required__{field_key}') or '').strip()
                required_override = None
                if required_choice == 'true':
                    required_override = True
                elif required_choice == 'false':
                    required_override = False
                TemplateInputDefault.objects.update_or_create(
                    template_type=canonical_template_type,
                    field_key=field_key,
                    defaults={
                        'default_text': form.cleaned_data.get(f'default__{field_key}', ''),
                        'required_override': required_override,
                    },
                )
            TemplateInputDefault.objects.filter(template_type=canonical_template_type).exclude(field_key__in=field_keys).delete()
            messages.success(request, f'{canonical_template_type} の入力欄初期値を更新しました。')
            return redirect('close_side:templates_list')
    else:
        form = TemplateInputDefaultsForm(template_type=canonical_template_type, initial=initial)

    field_rows = []
    for field in schema:
        field_key = str(field['key'])
        field_rows.append({
            'key': field_key,
            'label': str(field['label']),
            'input_type': str(field.get('input_type') or 'textarea'),
            'required': bool(field.get('required')),
            'bound_default_field': form[f'default__{field_key}'],
            'bound_required_field': form[f'required__{field_key}'],
        })

    aliases = [alias for alias, canonical in TEMPLATE_INPUT_SCHEMA_ALIASES.items() if canonical == canonical_template_type]
    return render(request, 'anonymizer_app/template_input_defaults_form.html', {
        'form': form,
        'template_type': canonical_template_type,
        'template_aliases': aliases,
        'field_rows': field_rows,
    })


def template_input_fields_edit(request, template_type):
    canonical_template_type = TEMPLATE_INPUT_SCHEMA_ALIASES.get(template_type, template_type)
    if canonical_template_type not in TEMPLATE_INPUT_SCHEMAS:
        return render(request, 'anonymizer_app/error.html', {'message': 'テンプレートが見つかりません'}, status=404)

    aliases = [alias for alias, canonical in TEMPLATE_INPUT_SCHEMA_ALIASES.items() if canonical == canonical_template_type]
    template_schema = get_template_input_schema(canonical_template_type)
    schema_map = {str(field.get('key') or ''): field for field in template_schema}
    existing_rows = {
        row.field_key: row
        for row in TemplateInputField.objects.filter(template_type=canonical_template_type)
    }
    newly_added_row_key = None

    if request.method == 'POST':
        parsed_rows = _parse_template_field_rows(request.POST)
        deleted_field_keys = _parse_deleted_template_field_keys(request.POST)
        editor_action = str(request.POST.get('editor_action') or '').strip()

        if editor_action == 'add_row':
            next_row_number = _next_new_template_field_row_number(parsed_rows)
            next_position = max(
                [int(row.get('position') or 0) for row in parsed_rows] or [-10]
            ) + 10
            parsed_rows.append({
                'row_key': f'new_{next_row_number}',
                'record_id': '',
                'field_key': '',
                'source_kind': 'new',
                'label': '',
                'input_type': 'textarea',
                'section_title': '',
                'required': False,
                'allow_other': False,
                'other_label': 'その他',
                'other_placeholder': '自由入力',
                'help_text': '',
                'textarea_rows': 3,
                'position': next_position,
                'order': len(parsed_rows),
            })
            newly_added_row_key = str(parsed_rows[-1].get('row_key') or '')
            field_rows = _template_field_editor_context(
                canonical_template_type,
                parsed_rows=parsed_rows,
                field_errors={},
                deleted_field_keys=deleted_field_keys,
            )
        else:
            field_errors: dict[str, str] = {}
            existing_keys = set(schema_map.keys()) | set(existing_rows.keys()) | set(deleted_field_keys)
            active_rows: list[dict[str, object]] = []

            for row in parsed_rows:
                row_key = str(row.get('row_key') or '')
                source_kind = str(row.get('source_kind') or 'new')
                label = str(row.get('label') or '').strip()
                input_type = str(row.get('input_type') or 'textarea').strip() or 'textarea'
                if not label:
                    if source_kind == 'new':
                        continue
                    field_errors[row_key] = '欄名を入力してください。'
                    continue

                field_key = str(row.get('field_key') or '').strip()
                if not field_key:
                    field_key = row_key if source_kind in {'builtin', 'db'} and row_key else _generate_template_field_key(existing_keys)
                existing_keys.add(field_key)

                active_rows.append({
                    'row_key': row_key,
                    'record_id': str(row.get('record_id') or '').strip(),
                    'field_key': field_key,
                    'source_kind': source_kind,
                    'label': label,
                    'input_type': input_type if input_type in FIELD_INPUT_TYPE_VALUES else 'textarea',
                    'section_title': str(row.get('section_title') or '').strip(),
                    'required': bool(row.get('required')),
                    'allow_other': bool(row.get('allow_other')),
                    'other_label': str(row.get('other_label') or '').strip() or 'その他',
                    'other_placeholder': str(row.get('other_placeholder') or '').strip() or '自由入力',
                    'help_text': str(row.get('help_text') or '').strip(),
                    'textarea_rows': max(1, _safe_int(row.get('textarea_rows'), default=3)),
                    'position': _safe_int(row.get('position'), default=_safe_int(row.get('order'), 0)),
                    'order': _safe_int(row.get('order'), 0),
                })

            active_rows.sort(key=lambda item: (int(item.get('position') or 0), int(item.get('order') or 0)))

            if not field_errors:
                active_field_keys = [str(row.get('field_key') or '').strip() for row in active_rows if str(row.get('field_key') or '').strip()]
                active_field_key_set = set(active_field_keys)

                with transaction.atomic():
                    for sort_index, row in enumerate(active_rows):
                        field_key = str(row.get('field_key') or '').strip()
                        input_type = str(row.get('input_type') or 'textarea').strip() or 'textarea'
                        defaults = {
                            'label': str(row.get('label') or '').strip(),
                            'input_type': input_type if input_type in FIELD_INPUT_TYPE_VALUES else 'textarea',
                            'section_title': str(row.get('section_title') or '').strip(),
                            'required': bool(row.get('required')),
                            'allow_other': bool(row.get('allow_other')) if input_type == 'checkbox_group' else False,
                            'other_label': str(row.get('other_label') or '').strip() or 'その他',
                            'other_placeholder': str(row.get('other_placeholder') or '').strip() or '自由入力',
                            'help_text': str(row.get('help_text') or '').strip(),
                            'textarea_rows': max(1, _safe_int(row.get('textarea_rows'), default=3)),
                            'sort_order': sort_index * 10,
                            'is_active': True,
                        }
                        TemplateInputField.objects.update_or_create(
                            template_type=canonical_template_type,
                            field_key=field_key,
                            defaults=defaults,
                        )

                        if input_type != 'checkbox_group':
                            TemplateInputCheckboxGroup.objects.filter(
                                template_type=canonical_template_type,
                                field_key=field_key,
                            ).delete()

                    for deleted_key in deleted_field_keys:
                        if deleted_key in active_field_key_set:
                            continue
                        deleted_row = existing_rows.get(deleted_key)
                        if deleted_row is not None:
                            if deleted_row.is_active:
                                deleted_row.is_active = False
                                deleted_row.save(update_fields=['is_active', 'updated_at'])
                            continue

                        base_field = schema_map.get(deleted_key)
                        if base_field is None:
                            continue

                        TemplateInputField.objects.update_or_create(
                            template_type=canonical_template_type,
                            field_key=deleted_key,
                            defaults={
                                'label': str(base_field.get('label') or deleted_key),
                                'input_type': str(base_field.get('input_type') or 'textarea'),
                                'section_title': str(base_field.get('section_title') or ''),
                                'required': bool(base_field.get('required')),
                                'allow_other': bool(base_field.get('allow_other')),
                                'other_label': str(base_field.get('other_label') or 'その他'),
                                'other_placeholder': str(base_field.get('other_placeholder') or '自由入力'),
                                'help_text': str(base_field.get('help_text') or ''),
                                'textarea_rows': max(1, _safe_int(base_field.get('textarea_rows'), default=3)),
                                'sort_order': _safe_int(base_field.get('sort_order'), 0),
                                'is_active': False,
                            },
                        )

                messages.success(request, f'{canonical_template_type} のテンプレート欄を更新しました。')
                return redirect('close_side:template_input_fields_edit', template_type=canonical_template_type)

            field_rows = _template_field_editor_context(
                canonical_template_type,
                parsed_rows=active_rows,
                field_errors=field_errors,
                deleted_field_keys=deleted_field_keys,
            )
    else:
        field_rows = _template_field_editor_context(canonical_template_type)
        deleted_field_keys = []

    next_position = 10
    if field_rows:
        next_position = max(int(row.get('position') or 0) for row in field_rows) + 10

    return render(request, 'anonymizer_app/template_input_fields_form.html', {
        'template_type': canonical_template_type,
        'template_aliases': aliases,
        'field_rows': field_rows,
        'field_input_type_choices': FIELD_INPUT_TYPE_CHOICES,
        'next_row_number': len(field_rows),
        'next_position': next_position,
        'deleted_field_keys': ','.join(deleted_field_keys),
        'newly_added_row_key': newly_added_row_key,
    })


def template_checkbox_options_edit(request, template_type):
    canonical_template_type = TEMPLATE_INPUT_SCHEMA_ALIASES.get(template_type, template_type)
    if canonical_template_type not in TEMPLATE_INPUT_SCHEMAS:
        return render(request, 'anonymizer_app/error.html', {'message': 'テンプレートが見つかりません'}, status=404)

    checkbox_fields = _checkbox_group_fields_for_template(canonical_template_type)
    if not checkbox_fields:
        return render(request, 'anonymizer_app/error.html', {'message': 'チェックボックス項目が見つかりません'}, status=404)

    aliases = [alias for alias, canonical in TEMPLATE_INPUT_SCHEMA_ALIASES.items() if canonical == canonical_template_type]

    if request.method == 'POST':
        parsed_rows_by_field: dict[str, list[dict[str, object]]] = {}
        field_errors: dict[str, str] = {}
        for field in checkbox_fields:
            field_key = str(field['key'])
            parsed_rows = _parse_checkbox_group_rows(request.POST, field_key)
            parsed_rows_by_field[field_key] = parsed_rows
            seen_texts: set[str] = set()
            for row in parsed_rows:
                text = str(row.get('text') or '').strip()
                if not text:
                    continue
                if text in seen_texts:
                    field_errors[field_key] = '同じ項目名が重複しています。'
                    break
                seen_texts.add(text)

        if not field_errors:
            with transaction.atomic():
                for field in checkbox_fields:
                    field_key = str(field['key'])
                    group = TemplateInputCheckboxGroup.objects.filter(
                        template_type=canonical_template_type,
                        field_key=field_key,
                    ).prefetch_related('options').first()
                    existing_options = {
                        str(option.pk): option
                        for option in group.options.all()
                    } if group is not None else {}
                    normalized_rows: list[dict[str, object]] = []
                    for order, row in enumerate(parsed_rows_by_field.get(field_key, [])):
                        row_id = str(row.get('id') or '').strip()
                        text = str(row.get('text') or '').strip()
                        position = _safe_int(row.get('position'), default=order * 10)
                        if not text:
                            continue
                        normalized_rows.append({
                            'row_id': row_id,
                            'text': text,
                            'position': position,
                        })

                    if group is None and not normalized_rows:
                        continue
                    if group is None:
                        group = TemplateInputCheckboxGroup.objects.create(
                            template_type=canonical_template_type,
                            field_key=field_key,
                        )
                        existing_options = {}

                    kept_option_ids: set[str] = {
                        str(row.get('row_id') or '').strip()
                        for row in normalized_rows
                        if str(row.get('row_id') or '').strip() in existing_options
                    }
                    for option_id, option in list(existing_options.items()):
                        if option_id not in kept_option_ids:
                            option.delete()

                    normalized_rows.sort(key=lambda row: (int(row.get('position') or 0), int(row.get('order') or 0)))
                    for sort_order, row in enumerate(normalized_rows):
                        row_id = str(row.get('row_id') or '').strip()
                        text = str(row.get('text') or '').strip()
                        if row_id and row_id in existing_options:
                            option = existing_options[row_id]
                            option.text = text
                            option.sort_order = sort_order
                            option.save(update_fields=['text', 'sort_order', 'updated_at'])
                            kept_option_ids.add(row_id)
                        else:
                            TemplateInputCheckboxOption.objects.create(
                                group=group,
                                text=text,
                                sort_order=sort_order,
                            )

                TemplateInputCheckboxGroup.objects.filter(template_type=canonical_template_type).exclude(
                    field_key__in=[str(field['key']) for field in checkbox_fields]
                ).delete()

            messages.success(request, f'{canonical_template_type} のチェックボックス項目を更新しました。')
            return redirect('close_side:template_checkbox_options_edit', template_type=canonical_template_type)

        field_rows = []
        for field in checkbox_fields:
            field_key = str(field['key'])
            group = TemplateInputCheckboxGroup.objects.filter(
                template_type=canonical_template_type,
                field_key=field_key,
            ).prefetch_related('options').first()
            field_rows.append({
                'field': field,
                'context': _build_checkbox_group_field_context(field, group, parsed_rows_by_field.get(field_key, [])),
                'error': field_errors.get(field_key, ''),
            })
    else:
        field_rows = []
        for field in checkbox_fields:
            field_key = str(field['key'])
            group = TemplateInputCheckboxGroup.objects.filter(
                template_type=canonical_template_type,
                field_key=field_key,
            ).prefetch_related('options').first()
            field_rows.append({
                'field': field,
                'context': _build_checkbox_group_field_context(field, group),
                'error': '',
            })

    return render(request, 'anonymizer_app/template_checkbox_options_form.html', {
        'template_type': canonical_template_type,
        'template_aliases': aliases,
        'field_rows': field_rows,
    })


@require_http_methods(["POST"])
def template_delete(request, pk):
    sync_templates_to_db()
    tpl = get_object_or_404(Template, pk=pk)
    source_filename = tpl.source_filename
    try:
        delete_template_source(source_filename)
        tpl.delete()
        _normalize_template_sort_order()
        _log_operation(request, 'template_deleted', 'Template', source_filename)
        messages.success(request, 'テンプレートを削除しました。')
    except Exception as e:
        messages.error(request, f'テンプレート削除に失敗しました: {e}')
    return redirect('close_side:templates_list')


def user_list(request):
    users = get_user_model().objects.order_by('username')
    return render(request, 'anonymizer_app/user_list.html', {'users': users})


def operation_logs(request):
    history_query = request.GET.get('q', '').strip()
    logs = list(OperationLog.objects.order_by('-created_at')[:HISTORY_LIMIT])
    logs = filter_history_items(logs, history_query, [
        'actor_username',
        'action',
        lambda log: operation_action_label(log.action),
        'target_type',
        'target_id',
        'source_ip',
        'import_source_ip',
        lambda log: log.get_result_display(),
        'error_message',
        'details',
        lambda log: log.created_at.strftime('%Y-%m-%d %H:%M:%S'),
    ])
    logs = decorate_operation_logs(logs)
    return render(request, 'anonymizer_app/operation_logs.html', {
        'logs': logs,
        'side_name': 'CloseSide',
        'history_query': history_query,
    })


def anonymization_rules(request):
    rule = AnonymizationRule.objects.order_by('-updated_at').first()
    if rule:
        text = rule.content
    else:
        rules_path = Path(__file__).resolve().parents[1] / 'anonymizer_app' / 'prompt_templates' / 'anonymization_rules.md'
        if not rules_path.exists():
            return HttpResponse('匿名化ルールが見つかりません', status=404)
        text = rules_path.read_text(encoding='utf-8')

    try:
        import markdown
        html = markdown.markdown(text)
        return render(request, 'anonymizer_app/anonymization_rules.html', {'rules_html': html})
    except Exception:
        return render(request, 'anonymizer_app/anonymization_rules.html', {'rules_text': text})


def api_template_preview(request, template_name):
    try:
        sync_templates_to_db()
        source = get_template_source_by_name(template_name)
        if source is None:
            return JsonResponse({'error': 'Template not found'}, status=404)
        return JsonResponse({
            'name': source.name,
            'template_type': source.template_type,
            'basic_content': source.basic_content or '',
            'additional_content': source.additional_content or '',
        })
    except Template.DoesNotExist:
        return JsonResponse({'error': 'Template not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def template_detail(request, template_name):
    try:
        sync_templates_to_db()
        source = get_template_source_by_name(template_name)
        if source is None:
            return render(request, 'anonymizer_app/error.html', {'message': 'テンプレートが見つかりません'}, status=404)
        template = Template.objects.filter(source_filename=source.source_filename).first()
        if template is None:
            return render(request, 'anonymizer_app/error.html', {'message': 'テンプレートが見つかりません'}, status=404)
        return render(request, 'anonymizer_app/template_detail.html', {
            'template': template,
        })
    except Template.DoesNotExist:
        return render(request, 'anonymizer_app/error.html', {'message': 'テンプレートが見つかりません'}, status=404)
