import json
import datetime
from pathlib import Path

from django.contrib import messages
from django.shortcuts import redirect, render

from anonymizer_app.forms import DMZImportForm, DMZListForm


def _close_to_open_dir() -> Path:
    return Path(__file__).resolve().parents[2] / 'dmz' / 'close_to_open'


def _logs_dir() -> Path:
    return Path(__file__).resolve().parent / 'logs'


def _safe_filename(filename: str) -> str:
    safe_name = Path(filename).name
    if safe_name != filename:
        raise ValueError('不正なファイル名です')
    return safe_name


def _list_dmz_files(dmz_dir: Path):
    if not dmz_dir.exists():
        return []

    files = []
    entries = sorted(dmz_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    for entry in entries:
        if entry.is_file():
            stat = entry.stat()
            files.append({
                'name': entry.name,
                'size': stat.st_size,
                'modified': datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
            })
    return files


def _import_dmz_file(filename: str) -> Path:
    filename = _safe_filename(filename)
    dmz_dir = _close_to_open_dir()
    local_path = dmz_dir / filename
    if not local_path.exists():
        raise FileNotFoundError(f'ファイルが見つかりません: {filename}')
    if not local_path.is_file():
        raise IsADirectoryError(f'ファイルではありません: {filename}')

    content = local_path.read_text(encoding='utf-8')
    logs_dir = _logs_dir()
    logs_dir.mkdir(exist_ok=True)
    local_copy = logs_dir / filename
    local_copy.write_text(content, encoding='utf-8')
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
                    files = _list_dmz_files(dmz_dir)
            except Exception as e:
                messages.error(request, f'DMZ ファイル一覧の取得に失敗しました: {e}')
    else:
        form = DMZListForm()
        try:
            files = _list_dmz_files(dmz_dir) if dmz_dir.exists() else []
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
                local_copy = _import_dmz_file(filename)
                messages.success(request, f'OpenSide にファイルを取り込みました: {filename}')
                return redirect('open_side:imported_prompt', filename=local_copy.name)
            except FileNotFoundError as e:
                messages.error(request, str(e))
                if request.POST.get('next') == 'list':
                    return redirect('open_side:dmz_list')
                return render(request, 'anonymizer_app/dmz_import.html', {'form': form})
            except Exception as e:
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
    })
