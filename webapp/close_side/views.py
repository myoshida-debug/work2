import datetime
import difflib
import json
import re
import uuid
from urllib.parse import urlencode
from pathlib import Path

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_http_methods

from anonymizer_app.forms import AnonymizeForm, DMZExportForm, DMZResultImportForm, PromptForm, TemplateForm, TemplateInputDefaultsForm
from anonymizer_app.history_utils import (
    HISTORY_LIMIT,
    decorate_operation_logs,
    filter_history_items,
    operation_action_label,
)
from anonymizer_app.models import AnonymizationRule, OperationLog, Prompt, RestoredResult, RestoreMetadata, Template, TemplateInputDefault
from anonymizer_app.modules.anonymize import anonymize_text, build_prompt_payload, restore_text
from anonymizer_app.network_policy import get_client_ip
from anonymizer_app.structured_input import (
    build_source_input_data,
    build_source_text_from_structured_input,
    build_source_text_from_source_input_data,
    build_structured_input_labels,
    collect_structured_input,
    normalize_source_input_data,
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
    structured_input: dict[str, str] | None = None,
    errors: dict[str, str] | None = None,
) -> list[dict[str, object]]:
    structured_input = structured_input or {}
    errors = errors or {}
    fields = []
    for field in get_template_input_schema(template_type):
        key = str(field['key'])
        if key in structured_input:
            value = str(structured_input.get(key, '') or '')
        else:
            value = str(field.get('default', '') or '')
        fields.append({
            **field,
            'value': value,
            'error': errors.get(key, ''),
        })
    return fields


def _anonymize_page_context(
    form: AnonymizeForm,
    *,
    template_type: str,
    input_mode: str,
    source_text: str = '',
    structured_input: dict[str, str] | None = None,
    structured_field_errors: dict[str, str] | None = None,
    structured_fields: list[dict[str, object]] | None = None,
    text_items: list[dict[str, object]] | None = None,
    restore_map: dict[str, str] | None = None,
    prompt_json: str = '',
    restore_json: str = '',
    source_id: str = '',
) -> dict[str, object]:
    structured_fields = structured_fields or _structured_field_context(template_type, structured_input, structured_field_errors)
    restore_map = restore_map or {}
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
        'template_input_schemas': get_template_input_schema_map(),
    }


def _metadata_for_user(source_id: str, user):
    return _owned_queryset(RestoreMetadata.objects.all(), user).filter(source_id=source_id).first()


def _build_result_preview(result_record: RestoredResult) -> dict[str, object]:
    result_text = result_record.result_text or ''
    restored_text = result_record.restored_text or ''
    has_result_text = bool(result_text.strip())
    has_restored_text = bool(restored_text.strip())
    result_json = result_record.result_json if isinstance(result_record.result_json, dict) else {}
    input_mode = result_json.get('metadata', {}).get('input_mode') or ''

    if has_result_text and has_restored_text:
        result_html, restored_html = highlight_changed_text(result_text, restored_text)
    else:
        result_html = mark_safe(escape(result_text)) if has_result_text else ''
        restored_html = mark_safe(escape(restored_text)) if has_restored_text else ''

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
        'result_html': result_html,
        'restored_html': restored_html,
        'has_result_text': has_result_text,
        'has_restored_text': has_restored_text,
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
    selected_preview = _build_result_preview(selected_result)
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
            source_text = build_source_text_from_source_input_data(prompt.source_input_data)
            transcript_source = str(source_input_data.get('transcript_source') or 'manual_input').strip() or 'manual_input'
            form = AnonymizeForm(initial={
                'template': template_name,
                'input_mode': input_mode,
                'text': source_text if input_mode != 'voice' else '',
                'transcript_text': source_text if input_mode == 'voice' else '',
                'transcript_source': transcript_source if input_mode == 'voice' else 'manual_input',
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
            ))

    form = AnonymizeForm(request.POST or None)
    template_name = _selected_template_name(form)
    input_mode = _selected_input_mode(form)
    structured_input: dict[str, str] = {}
    structured_field_errors: dict[str, str] = {}
    source_text = ''

    if request.method == 'POST' and form.is_valid():
        template_name = form.cleaned_data['template']
        input_mode = form.cleaned_data.get('input_mode') or 'free'
        transcript_source = 'manual_input'

        if input_mode == 'structured':
            structured_input = collect_structured_input(request.POST)
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
                ))

        result = anonymize_text(source_text, template_name)
        anonymized_text = result.text
        restore_map = result.restore_map

        source_id = _make_prompt_source_id(template_name)
        payload = build_prompt_payload(template_name, {'text': anonymized_text}, source_id, title=template_name)
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
        ))

    structured_fields = _structured_field_context(template_name)
    return render(request, 'anonymizer_app/index.html', _anonymize_page_context(
        form,
        template_type=template_name,
        input_mode=input_mode,
        source_text=source_text,
        structured_fields=structured_fields,
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
    if input_mode == 'voice' and not source_text:
        return JsonResponse({'error': '文字起こし結果が空です。録音または入力してください。'}, status=400)
    structured_input_data = data.get('structured_input')
    if isinstance(structured_input_data, dict):
        structured_input = {str(key): str(value or '').strip() for key, value in structured_input_data.items()}
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
    )

    prompt_payload = build_prompt_payload(template_type, {'text': anonymized_text}, source_id, title=template_type)
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

    restored_text = restore_text(result_text_value, metadata.restore_map)
    template_type = result_payload.get('template_type') or metadata.template_type
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
    metadata.status = 'imported_to_close'
    metadata.save(update_fields=['status', 'updated_at'])
    try:
        result_path.unlink()
    except OSError as e:
        messages.warning(request, f'DMZ返却ファイルの削除に失敗しました: {e}')
    result_html, restored_html = highlight_changed_text(result_text_value, restored_text)
    _log_operation(request, 'result_imported_to_close', 'RestoredResult', str(result_record.pk), {
        'filename': filename,
        'source_id': source_id,
    })

    messages.success(request, f'返却JSONを取り込み、復元しました: {filename}')
    return render(request, 'anonymizer_app/restored_result.html', {
        'record': result_record,
        'filename': filename,
        'source_id': source_id,
        'template_type': template_type,
        'input_mode': input_mode,
        'result_text': result_text_value,
        'restored_text': restored_text,
        'result_html': result_html,
        'restored_html': restored_html,
        'result_json': json.dumps(result_payload, ensure_ascii=False, indent=2),
        'restore_map_items': list(metadata.restore_map.items()),
    })


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
    result = sync_templates_to_db()
    templates = sorted(result['templates'], key=lambda template: (template.template_type, template.name))
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


@require_http_methods(["POST"])
def template_delete(request, pk):
    sync_templates_to_db()
    tpl = get_object_or_404(Template, pk=pk)
    source_filename = tpl.source_filename
    try:
        delete_template_source(source_filename)
        tpl.delete()
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
        return render(request, 'anonymizer_app/template_detail.html', {'template': template})
    except Template.DoesNotExist:
        return render(request, 'anonymizer_app/error.html', {'message': 'テンプレートが見つかりません'}, status=404)
