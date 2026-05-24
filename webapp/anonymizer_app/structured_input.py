from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from .template_input_schemas import get_template_input_schema


STRUCTURED_INPUT_PREFIX = 'structured__'
CHECKBOX_GROUP_INPUT_TYPE = 'checkbox_group'


def _stringify_value(value: object) -> str:
    if value is None:
        return ''
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return json.dumps(list(value), ensure_ascii=False)
    return str(value).strip()


def _coerce_selected_values(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        raw_values = value.get('selected') or value.get('values') or value.get('items') or []
    else:
        raw_values = value

    if isinstance(raw_values, str):
        iterable: list[object] = [raw_values]
    elif isinstance(raw_values, Sequence) and not isinstance(raw_values, (str, bytes)):
        iterable = list(raw_values)
    else:
        iterable = [raw_values]

    selected: list[str] = []
    for item in iterable:
        text = _stringify_value(item)
        if text:
            selected.append(text)
    return list(dict.fromkeys(selected))


def _normalize_checkbox_group_value(value: object) -> dict[str, object]:
    selected: list[str] = []
    other_text = ''
    other_checked = False
    text = ''

    if isinstance(value, Mapping):
        text = _stringify_value(value.get('text'))
        selected = _coerce_selected_values(value)
        other_text = _stringify_value(value.get('other') or value.get('other_text'))
        other_checked = bool(value.get('other_checked') or value.get('otherSelected') or value.get('has_other'))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        selected = _coerce_selected_values(value)
    else:
        text = _stringify_value(value)

    if other_text:
        other_checked = True

    return {
        'text': text,
        'selected': selected,
        'other': other_text,
        'other_checked': other_checked,
    }


def _field_map(template_type: str) -> dict[str, dict[str, object]]:
    return {
        str(field.get('key') or ''): field
        for field in get_template_input_schema(template_type)
        if str(field.get('key') or '')
    }


def _field_uses_checkbox_options(field: Mapping[str, object] | None) -> bool:
    if not isinstance(field, Mapping):
        return False
    return bool(field.get('options')) or str(field.get('input_type') or 'textarea') == CHECKBOX_GROUP_INPUT_TYPE


def _field_section_title(field: Mapping[str, object] | None) -> str:
    if not isinstance(field, Mapping):
        return ''
    return _stringify_value(field.get('section_title'))


def _checkbox_option_display_map(field: Mapping[str, object] | None) -> dict[str, str]:
    if not isinstance(field, Mapping):
        return {}

    display_map: dict[str, str] = {}
    for option in field.get('options') or []:
        if isinstance(option, Mapping):
            value = _stringify_value(option.get('value'))
            label = _stringify_value(option.get('label') or option.get('value'))
        else:
            value = _stringify_value(option)
            label = value
        if not value:
            continue
        display_map[value] = label or value
    return display_map


def _display_checkbox_value(field: Mapping[str, object] | None, value: object) -> str:
    text = _stringify_value(value)
    if not text:
        return ''
    return _checkbox_option_display_map(field).get(text, text)


def _compose_checkbox_group_text(
    field: Mapping[str, object] | None,
    selected_values: Sequence[str],
    other_text: str,
    other_checked: bool,
) -> str:
    label = str(field.get('other_label') or 'その他') if isinstance(field, Mapping) else 'その他'
    lines = [f'・{_display_checkbox_value(field, item)}' for item in selected_values if str(item).strip()]
    if other_text:
        lines.append(f'・{label}: {other_text}')
    elif other_checked:
        lines.append(f'・{label}')
    return '\n'.join(lines).strip()


def _normalize_field_value(field_map: dict[str, dict[str, object]], field_key: str, value: object) -> object:
    field = field_map.get(field_key)
    if _field_uses_checkbox_options(field):
        normalized = _normalize_checkbox_group_value(value)
        text_value = _stringify_value(normalized.get('text'))
        if not text_value:
            text_value = _compose_checkbox_group_text(
                field,
                normalized.get('selected') or [],
                _stringify_value(normalized.get('other')),
                bool(normalized.get('other_checked')),
            )
        normalized['text'] = text_value
        return normalized
    return _stringify_value(value)


def normalize_structured_input(template_type: str, structured_input: Mapping[str, object] | None) -> dict[str, object]:
    if not isinstance(structured_input, Mapping):
        return {}

    normalized: dict[str, object] = {}
    field_map = _field_map(template_type)
    for key, value in structured_input.items():
        field_key = str(key)
        normalized[field_key] = _normalize_field_value(field_map, field_key, value)
    return normalized


def _is_truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def collect_structured_input(template_type: str, post_data: Mapping[str, object]) -> dict[str, object]:
    structured_input: dict[str, object] = {}
    for field in get_template_input_schema(template_type):
        key = str(field['key'])
        field_name = f'{STRUCTURED_INPUT_PREFIX}{key}'
        if _field_uses_checkbox_options(field):
            text_name = f'{field_name}__text'
            text_value = _stringify_value(post_data.get(text_name))
            selected_values: list[str] = []
            if hasattr(post_data, 'getlist'):
                raw_values = getattr(post_data, 'getlist')(field_name)
            else:
                raw_values = post_data.get(field_name, [])
            if isinstance(raw_values, str):
                raw_iterable: list[object] = [raw_values]
            elif isinstance(raw_values, Sequence) and not isinstance(raw_values, (str, bytes)):
                raw_iterable = list(raw_values)
            else:
                raw_iterable = [raw_values]
            for item in raw_iterable:
                text = _stringify_value(item)
                if text:
                    selected_values.append(text)

            other_text = _stringify_value(post_data.get(f'{field_name}__other'))
            other_checked = _is_truthy(post_data.get(f'{field_name}__other_checked')) or bool(other_text)
            structured_input[key] = {
                'text': text_value,
                'selected': list(dict.fromkeys(selected_values)),
                'other': other_text,
                'other_checked': other_checked,
            }
            continue

        structured_input[key] = _stringify_value(post_data.get(field_name))

    return normalize_structured_input(template_type, structured_input)


def validate_structured_input(template_type: str, structured_input: dict[str, object]) -> dict[str, str]:
    errors: dict[str, str] = {}
    normalized_structured_input = normalize_structured_input(template_type, structured_input)

    for field in get_template_input_schema(template_type):
        key = str(field['key'])
        label = str(field['label'])
        required = bool(field.get('required'))
        is_checkbox_field = _field_uses_checkbox_options(field)
        value = normalized_structured_input.get(key)

        if is_checkbox_field:
            value_map = value if isinstance(value, dict) else {}
            text_value = _stringify_value(value_map.get('text'))
            selected_values = value_map.get('selected') or []
            other_text = _stringify_value(value_map.get('other'))
            other_checked = bool(value_map.get('other_checked'))

            if required and not text_value and not selected_values and not other_text:
                errors[key] = f'「{label}」は少なくとも1つ選択してください。'
                continue
            if other_checked and not other_text:
                errors[key] = f'「{label}」の「その他」を選ぶ場合は内容を入力してください。'
            continue

        text_value = _stringify_value(value)
        if required and not text_value:
            errors[key] = f'「{label}」は必須項目です。入力するか、「記載なし」と明記してください。'

    return errors


def build_structured_input_labels(template_type: str, structured_input: dict[str, object]) -> list[str]:
    labels: list[str] = []
    normalized_structured_input = normalize_structured_input(template_type, structured_input)

    for field in get_template_input_schema(template_type):
        key = str(field['key'])
        label = str(field['label'])
        is_checkbox_field = _field_uses_checkbox_options(field)
        value = normalized_structured_input.get(key)

        if is_checkbox_field:
            value_map = value if isinstance(value, dict) else {}
            text_value = _stringify_value(value_map.get('text'))
            selected_values = value_map.get('selected') or []
            other_text = _stringify_value(value_map.get('other'))
            if text_value or selected_values or other_text:
                labels.append(label)
            continue

        if _stringify_value(value):
            labels.append(label)

    return labels


def build_source_text_from_structured_input(template_type: str, structured_input: dict[str, object]) -> str:
    blocks: list[str] = []
    normalized_structured_input = normalize_structured_input(template_type, structured_input)
    current_section_title = ''
    current_section_blocks: list[str] = []
    current_section_has_content = False

    def flush_section() -> None:
        nonlocal current_section_title, current_section_blocks, current_section_has_content
        if current_section_title and current_section_has_content:
            blocks.append(f'## {current_section_title}\n\n' + '\n\n'.join(current_section_blocks))
        elif current_section_blocks:
            blocks.extend(current_section_blocks)
        current_section_title = ''
        current_section_blocks = []
        current_section_has_content = False

    for field in get_template_input_schema(template_type):
        key = str(field['key'])
        label = str(field['label'])
        section_title = _field_section_title(field)
        is_checkbox_field = _field_uses_checkbox_options(field)
        value = normalized_structured_input.get(key)

        if is_checkbox_field:
            value_map = value if isinstance(value, dict) else {}
            text_value = _stringify_value(value_map.get('text'))
            selected_values = [str(item).strip() for item in (value_map.get('selected') or []) if str(item).strip()]
            other_text = _stringify_value(value_map.get('other'))
            other_checked = bool(value_map.get('other_checked'))

            field_text = text_value or _compose_checkbox_group_text(field, selected_values, other_text, other_checked)
        else:
            field_text = _stringify_value(value)

        if field_text:
            if section_title:
                if section_title != current_section_title:
                    flush_section()
                    current_section_title = section_title
                if label == section_title:
                    current_section_blocks.append(field_text)
                else:
                    current_section_blocks.append(f'### {label}\n{field_text}')
                current_section_has_content = True
            else:
                flush_section()
                blocks.append(f'【{label}】\n{field_text}')

    flush_section()

    return '\n\n'.join(blocks)


def build_source_input_data(
    template_type: str,
    input_mode: str,
    source_text: str,
    structured_input: dict[str, object] | None = None,
    transcript_source: str = '',
    patient: dict[str, object] | None = None,
) -> dict[str, object]:
    normalized_input_mode = str(input_mode or 'free').strip() or 'free'
    normalized_text = str(source_text or '').strip()
    normalized_structured_input: dict[str, object] = {}
    if normalized_input_mode == 'structured' and structured_input:
        normalized_structured_input = normalize_structured_input(template_type, structured_input)

    payload: dict[str, object] = {
        'template_type': str(template_type or '').strip(),
        'input_mode': normalized_input_mode,
        'text': normalized_text,
        'structured_input': normalized_structured_input,
    }
    normalized_transcript_source = str(transcript_source or '').strip()
    if normalized_transcript_source:
        payload['transcript_source'] = normalized_transcript_source
    if isinstance(patient, Mapping):
        payload['patient'] = dict(patient)
        patient_id = str(patient.get('patient_id') or '').strip()
        if patient_id:
            payload['patient_id'] = patient_id
    return payload


def normalize_source_input_data(source_input_data: object) -> dict[str, object]:
    if not isinstance(source_input_data, Mapping):
        return {
            'template_type': '',
            'input_mode': 'free',
            'text': '',
            'structured_input': {},
            'transcript_source': '',
            'patient': {},
            'patient_id': '',
        }

    template_type = str(source_input_data.get('template_type') or '').strip()
    structured_input_data = source_input_data.get('structured_input') or {}
    patient_data = source_input_data.get('patient') or {}
    structured_input: dict[str, object] = {}
    if isinstance(structured_input_data, Mapping):
        structured_input = normalize_structured_input(template_type, structured_input_data)

    normalized_patient: dict[str, object] = {}
    if isinstance(patient_data, Mapping):
        normalized_patient = dict(patient_data)
        normalized_patient['patient_id'] = str(normalized_patient.get('patient_id') or '').strip()
        normalized_patient['surname'] = str(normalized_patient.get('surname') or '').strip()
        normalized_patient['given_name'] = str(normalized_patient.get('given_name') or '').strip()
        normalized_patient['kana_surname'] = str(normalized_patient.get('kana_surname') or '').strip()
        normalized_patient['kana_given_name'] = str(normalized_patient.get('kana_given_name') or '').strip()
        normalized_patient['primary_diagnosis'] = str(normalized_patient.get('primary_diagnosis') or '').strip()
        normalized_patient['birth_date'] = str(normalized_patient.get('birth_date') or '').strip()
        normalized_patient['sex'] = str(normalized_patient.get('sex') or '').strip()

    return {
        'template_type': template_type,
        'input_mode': str(source_input_data.get('input_mode') or 'free').strip() or 'free',
        'text': str(source_input_data.get('text') or '').strip(),
        'structured_input': structured_input,
        'transcript_source': str(source_input_data.get('transcript_source') or '').strip(),
        'patient': normalized_patient,
        'patient_id': str(source_input_data.get('patient_id') or normalized_patient.get('patient_id') or '').strip(),
    }


def build_source_text_from_source_input_data(source_input_data: object) -> str:
    normalized = normalize_source_input_data(source_input_data)
    template_type = str(normalized.get('template_type') or '')
    input_mode = str(normalized.get('input_mode') or 'free')
    source_text = str(normalized.get('text') or '')
    if source_text:
        return source_text
    if input_mode == 'structured':
        structured_input = normalized.get('structured_input') or {}
        if isinstance(structured_input, dict):
            return build_source_text_from_structured_input(template_type, structured_input)
    return source_text
