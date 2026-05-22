from __future__ import annotations

from collections.abc import Mapping

from .template_input_schemas import get_template_input_schema


STRUCTURED_INPUT_PREFIX = 'structured__'


def collect_structured_input(post_data: Mapping[str, object]) -> dict[str, str]:
    structured_input: dict[str, str] = {}
    for key, value in post_data.items():
        if not str(key).startswith(STRUCTURED_INPUT_PREFIX):
            continue
        field_key = str(key)[len(STRUCTURED_INPUT_PREFIX):]
        structured_input[field_key] = str(value or '').strip()
    return structured_input


def validate_structured_input(template_type: str, structured_input: dict[str, str]) -> dict[str, str]:
    errors: dict[str, str] = {}
    for field in get_template_input_schema(template_type):
        key = str(field['key'])
        label = str(field['label'])
        required = bool(field.get('required'))
        value = str(structured_input.get(key, '') or '').strip()
        if required and not value:
            errors[key] = f'「{label}」は必須項目です。入力するか、「記載なし」と明記してください。'
    return errors


def build_structured_input_labels(template_type: str, structured_input: dict[str, str]) -> list[str]:
    labels: list[str] = []
    for field in get_template_input_schema(template_type):
        key = str(field['key'])
        label = str(field['label'])
        value = str(structured_input.get(key, '') or '').strip()
        if value:
            labels.append(label)
    return labels


def build_source_text_from_structured_input(template_type: str, structured_input: dict[str, str]) -> str:
    blocks: list[str] = []
    for field in get_template_input_schema(template_type):
        key = str(field['key'])
        label = str(field['label'])
        value = str(structured_input.get(key, '') or '').strip()
        if not value:
            continue
        blocks.append(f'【{label}】\n{value}')
    return '\n\n'.join(blocks)


def build_source_input_data(
    template_type: str,
    input_mode: str,
    source_text: str,
    structured_input: dict[str, str] | None = None,
    transcript_source: str = '',
) -> dict[str, object]:
    normalized_input_mode = str(input_mode or 'free').strip() or 'free'
    normalized_text = str(source_text or '').strip()
    normalized_structured_input: dict[str, str] = {}
    if normalized_input_mode == 'structured' and structured_input:
        for key, value in structured_input.items():
            normalized_structured_input[str(key)] = str(value or '').strip()

    payload = {
        'template_type': str(template_type or '').strip(),
        'input_mode': normalized_input_mode,
        'text': normalized_text,
        'structured_input': normalized_structured_input,
    }
    normalized_transcript_source = str(transcript_source or '').strip()
    if normalized_transcript_source:
        payload['transcript_source'] = normalized_transcript_source
    return payload


def normalize_source_input_data(source_input_data: object) -> dict[str, object]:
    if not isinstance(source_input_data, Mapping):
        return {
            'template_type': '',
            'input_mode': 'free',
            'text': '',
            'structured_input': {},
            'transcript_source': '',
        }

    structured_input_data = source_input_data.get('structured_input') or {}
    structured_input: dict[str, str] = {}
    if isinstance(structured_input_data, Mapping):
        for key, value in structured_input_data.items():
            structured_input[str(key)] = str(value or '').strip()

    return {
        'template_type': str(source_input_data.get('template_type') or '').strip(),
        'input_mode': str(source_input_data.get('input_mode') or 'free').strip() or 'free',
        'text': str(source_input_data.get('text') or '').strip(),
        'structured_input': structured_input,
        'transcript_source': str(source_input_data.get('transcript_source') or '').strip(),
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
