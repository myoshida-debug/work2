import json
import datetime
import re
from pathlib import Path

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from anonymizer_app.forms import ChatGPTResultForm, DMZImportForm, DMZListForm
from anonymizer_app.history_utils import (
    HISTORY_LIMIT,
    decorate_operation_logs,
    filter_history_items,
    operation_action_label,
)
from anonymizer_app.models import OperationLog, Prompt, RestoreMetadata
from anonymizer_app.modules.anonymize import build_result_payload
from anonymizer_app.network_policy import get_client_ip


def _close_to_open_dir() -> Path:
    return Path(__file__).resolve().parents[2] / 'dmz' / 'close_to_open'


def _open_to_close_dir() -> Path:
    return Path(__file__).resolve().parents[2] / 'dmz' / 'open_to_close'


def _logs_dir() -> Path:
    return Path(__file__).resolve().parent / 'logs'


def _safe_filename(filename: str) -> str:
    safe_name = Path(filename).name
    if safe_name != filename:
        raise ValueError('不正なファイル名です')
    return safe_name


def _is_admin(user) -> bool:
    return bool(user.is_staff or user.is_superuser)


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


def _list_dmz_files(dmz_dir: Path, user=None):
    if not dmz_dir.exists():
        return []

    files = []
    entries = sorted(dmz_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
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
                'source_id': metadata.get('source_id') or payload.get('id') or '',
                'owner_username': metadata.get('owner_username') or '',
                'template_type': payload.get('template_type') or metadata.get('template_type') or '',
            })
    return files


def _safe_token(value: str) -> str:
    token = re.sub(r'[\\/\s]+', '_', value.strip())
    token = re.sub(r'[^\w.\-（）()ぁ-んァ-ヶ一-龥ー]', '_', token)
    return token.strip('._') or 'result'


def menu(request):
    dmz_files = _list_dmz_files(_close_to_open_dir(), request.user)[:5]
    return render(request, 'anonymizer_app/open_menu.html', {'dmz_files': dmz_files})


def _import_dmz_file(filename: str, request) -> Path:
    user = request.user
    filename = _safe_filename(filename)
    dmz_dir = _close_to_open_dir()
    local_path = dmz_dir / filename
    if not local_path.exists():
        raise FileNotFoundError(f'ファイルが見つかりません: {filename}')
    if not local_path.is_file():
        raise IsADirectoryError(f'ファイルではありません: {filename}')

    content = local_path.read_text(encoding='utf-8')
    payload = json.loads(content)
    if not _payload_visible_to_user(payload, user):
        raise PermissionError('このプロンプトを取り込む権限がありません。')

    logs_dir = _logs_dir()
    logs_dir.mkdir(exist_ok=True)
    local_copy = logs_dir / filename
    local_copy.write_text(content, encoding='utf-8')
    local_path.unlink()

    source_id = payload.get('metadata', {}).get('source_id') or payload.get('id') or ''
    if source_id:
        RestoreMetadata.objects.filter(source_id=source_id).update(status='imported_to_open', updated_at=timezone.now())
        Prompt.objects.filter(source_id=source_id).update(status='imported_to_open', updated_at=timezone.now())
        _log_operation(request, 'prompt_imported_to_open', 'RestoreMetadata', source_id, {'filename': filename})
    return local_copy


def dmz_list(request):
    dmz_dir = _close_to_open_dir()
    files = None

    if request.method == 'POST':
        form = DMZListForm(request.POST)
        if form.is_valid():
            try:
                if not dmz_dir.exists():
                    messages.error(request, f'DMZディレクトリが見つかりません: {dmz_dir}')
                else:
                    files = _list_dmz_files(dmz_dir, request.user)
            except Exception as e:
                messages.error(request, f'DMZ ファイル一覧の取得に失敗しました: {e}')
    else:
        form = DMZListForm()
        try:
            files = _list_dmz_files(dmz_dir, request.user) if dmz_dir.exists() else []
        except Exception as e:
            messages.warning(request, f'DMZ ファイル一覧の取得に失敗: {e}')

    return render(request, 'anonymizer_app/dmz_list.html', {
        'form': form,
        'files': files,
        'dmz_path': str(dmz_dir),
    })


def dmz_import(request):
    if request.method == 'POST':
        form = DMZImportForm(request.POST)
        if form.is_valid():
            filename = form.cleaned_data['filename']

            try:
                local_copy = _import_dmz_file(filename, request)
                messages.success(request, f'OpenSide にファイルを取り込みました: {filename}')
                return redirect('open_side:imported_prompt', filename=local_copy.name)
            except FileNotFoundError as e:
                _log_operation(
                    request,
                    'prompt_imported_to_open',
                    'RestoreMetadata',
                    filename,
                    {'filename': filename},
                    result='failure',
                    error_message=str(e),
                )
                messages.error(request, str(e))
                if request.POST.get('next') == 'list':
                    return redirect('open_side:dmz_list')
                return render(request, 'anonymizer_app/dmz_import.html', {'form': form})
            except Exception as e:
                _log_operation(
                    request,
                    'prompt_imported_to_open',
                    'RestoreMetadata',
                    filename,
                    {'filename': filename},
                    result='failure',
                    error_message=str(e),
                )
                messages.error(request, f'ファイル取り込みに失敗しました: {e}')
                if request.POST.get('next') == 'list':
                    return redirect('open_side:dmz_list')
                return render(request, 'anonymizer_app/dmz_import.html', {'form': form})
    else:
        form = DMZImportForm()
    return render(request, 'anonymizer_app/dmz_import.html', {'form': form})


def imported_prompt(request, filename):
    try:
        filename = _safe_filename(filename)
    except ValueError as e:
        messages.error(request, str(e))
        return redirect('open_side:dmz_list')

    imported_path = _logs_dir() / filename
    if not imported_path.exists():
        messages.error(request, f'取り込み済みファイルが見つかりません: {filename}')
        return redirect('open_side:dmz_list')

    raw_text = imported_path.read_text(encoding='utf-8')
    payload = None
    prompt_text = raw_text
    source_id = ''
    template_type = ''

    try:
        payload = json.loads(raw_text)
        if not _payload_visible_to_user(payload, request.user):
            messages.error(request, 'このプロンプトを表示する権限がありません。')
            return redirect('open_side:dmz_list')
        prompt_text = (
            payload.get('prompt_text')
            or payload.get('prompt')
            or payload.get('content', {}).get('text')
            or raw_text
        )
        source_id = payload.get('metadata', {}).get('source_id') or payload.get('id') or ''
        template_type = payload.get('template_type') or payload.get('metadata', {}).get('template_type') or ''
    except json.JSONDecodeError:
        messages.warning(request, 'JSON として解析できなかったため、ファイル本文をそのまま表示します。')

    return render(request, 'anonymizer_app/imported_prompt.html', {
        'filename': filename,
        'imported_path': str(imported_path),
        'prompt_text': prompt_text,
        'raw_text': raw_text,
        'source_id': source_id,
        'template_type': template_type,
        'is_json': payload is not None,
        'result_form': ChatGPTResultForm(),
    })


@require_http_methods(["POST"])
def create_result(request, filename):
    try:
        filename = _safe_filename(filename)
    except ValueError as e:
        messages.error(request, str(e))
        return redirect('open_side:dmz_list')

    imported_path = _logs_dir() / filename
    if not imported_path.exists():
        messages.error(request, f'取り込み済みファイルが見つかりません: {filename}')
        return redirect('open_side:dmz_list')

    raw_text = imported_path.read_text(encoding='utf-8')
    try:
        prompt_payload = json.loads(raw_text)
    except json.JSONDecodeError:
        _log_operation(
            request,
            'result_sent_to_dmz',
            'RestoreMetadata',
            filename,
            {'filename': filename},
            result='failure',
            error_message='取り込み元がJSONではないため、source_idを取得できません',
        )
        messages.error(request, '取り込み元がJSONではないため、source_idを取得できません。')
        return redirect('open_side:imported_prompt', filename=filename)
    if not _payload_visible_to_user(prompt_payload, request.user):
        _log_operation(
            request,
            'result_sent_to_dmz',
            'RestoreMetadata',
            filename,
            {'filename': filename},
            result='failure',
            error_message='返却JSONを作成する権限がありません',
        )
        messages.error(request, 'このプロンプトから返却JSONを作成する権限がありません。')
        return redirect('open_side:dmz_list')

    source_id = prompt_payload.get('metadata', {}).get('source_id') or prompt_payload.get('id') or ''
    if not source_id:
        _log_operation(
            request,
            'result_sent_to_dmz',
            'RestoreMetadata',
            filename,
            {'filename': filename},
            result='failure',
            error_message='取り込み元JSONに source_id がありません',
        )
        messages.error(request, '取り込み元JSONに source_id がありません。')
        return redirect('open_side:imported_prompt', filename=filename)

    form = ChatGPTResultForm(request.POST)
    if not form.is_valid():
        _log_operation(
            request,
            'result_sent_to_dmz',
            'RestoreMetadata',
            source_id,
            {'filename': filename, 'source_id': source_id},
            result='failure',
            error_message='ChatGPT生成結果が未入力です',
        )
        messages.error(request, 'ChatGPT生成結果を入力してください。')
        return redirect('open_side:imported_prompt', filename=filename)

    result_text = form.cleaned_data['result_text']
    reviewer = form.cleaned_data.get('reviewer') or ''
    template_type = prompt_payload.get('template_type') or prompt_payload.get('metadata', {}).get('template_type') or ''
    result_payload = build_result_payload(source_id, result_text, reviewer)
    result_payload['template_type'] = template_type
    result_payload['metadata']['template_type'] = template_type
    result_payload['metadata']['source_prompt_file'] = filename
    result_payload['metadata']['owner_user_id'] = prompt_payload.get('metadata', {}).get('owner_user_id')
    result_payload['metadata']['owner_username'] = prompt_payload.get('metadata', {}).get('owner_username') or ''
    result_payload['metadata']['returned_by'] = request.user.get_username()
    result_payload['metadata']['returned_at'] = datetime.datetime.now().isoformat()

    output_dir = _open_to_close_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    output_filename = f'result_{_safe_token(source_id)}_{timestamp}.json'
    output_path = output_dir / output_filename
    output_path.write_text(json.dumps(result_payload, ensure_ascii=False, indent=2), encoding='utf-8')
    RestoreMetadata.objects.filter(source_id=source_id).update(status='returned_to_dmz', updated_at=timezone.now())
    _log_operation(request, 'result_sent_to_dmz', 'RestoreMetadata', source_id, {'filename': output_filename})

    messages.success(request, f'CloseSide 返却DMZへ出力しました: {output_filename}')
    return render(request, 'anonymizer_app/result_returned.html', {
        'filename': filename,
        'output_filename': output_filename,
        'output_path': str(output_path),
        'source_id': source_id,
        'template_type': template_type,
        'result_json': json.dumps(result_payload, ensure_ascii=False, indent=2),
        'result_text': result_text,
    })


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
        'side_name': 'OpenSide',
        'history_query': history_query,
    })
