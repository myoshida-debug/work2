import difflib
import json
import uuid
import datetime
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse
from django.utils.html import escape
from django.utils.safestring import mark_safe
from .forms import AnonymizeForm
from .models import RestoreMetadata, Prompt, Template
from .forms import PromptForm, TemplateForm
from anonymizer_app.modules.anonymize import anonymize_text, build_prompt_payload
from .prompt_template_store import (
    get_template_source_by_filename,
    get_template_source_by_name,
    load_basic_template,
    sync_templates_to_db,
    write_template_source,
)
from close_side.views import _sanitize_prompt_payload_for_dmz
import os
from django.contrib import messages
from pathlib import Path

try:
    import paramiko
except Exception:
    paramiko = None
from django.views.decorators.http import require_http_methods
from .forms import DMZExportForm, DMZImportForm, DMZListForm
from django.template import loader


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


def home(request):
    if request.method == 'POST':
        form = AnonymizeForm(request.POST)
        if form.is_valid():
            template_type = form.cleaned_data['template']
            original_text = form.cleaned_data['text']
            result = anonymize_text(original_text, template_type)
            anonymized_text = result.text
            restore_map = result.restore_map

            source_id = f'prompt_{template_type.replace(" ", "_")}_{uuid.uuid4().hex[:8]}'
            payload = build_prompt_payload(template_type, {'text': anonymized_text}, source_id)
            payload['metadata']['created_at'] = None
            payload = _sanitize_prompt_payload_for_dmz(payload)
            prompt_json = payload
            restore_data = {
                'source_id': source_id,
                'restore_map': restore_map,
            }
            original_html, anonymized_html = highlight_changed_text(original_text, anonymized_text)
            text_items = [{
                'label': '入力テキスト',
                'original': original_text,
                'anonymized': anonymized_text,
                'original_html': original_html,
                'anonymized_html': anonymized_html,
            }]

            RestoreMetadata.objects.create(
                source_id=source_id,
                template_type=template_type,
                restore_map=restore_map,
                prompt_json=prompt_json,
            )

            return render(request, 'anonymizer_app/result.html', {
                'form': form,
                'template_type': template_type,
                'text_items': text_items,
                'restore_map': restore_map,
                'restore_map_items': list(restore_map.items()),
                'prompt_json': json.dumps(prompt_json, ensure_ascii=False, indent=2),
                'restore_json': json.dumps(restore_data, ensure_ascii=False, indent=2),
                'source_id': source_id,
            })
    else:
        form = AnonymizeForm()
    return render(request, 'anonymizer_app/index.html', {'form': form})


def download_prompt(request, source_id):
    metadata = get_object_or_404(RestoreMetadata, source_id=source_id)
    payload = _sanitize_prompt_payload_for_dmz(metadata.prompt_json or {})
    response = HttpResponse(json.dumps(payload, ensure_ascii=False, indent=2), content_type='application/json')
    response['Content-Disposition'] = f'attachment; filename="{metadata.source_id}.json"'
    return response


def download_restore(request, source_id):
    metadata = get_object_or_404(RestoreMetadata, source_id=source_id)
    payload = {
        'source_id': metadata.source_id,
        'restore_map': metadata.restore_map,
    }
    response = HttpResponse(json.dumps(payload, ensure_ascii=False, indent=2), content_type='application/json')
    response['Content-Disposition'] = f'attachment; filename="restore_{metadata.source_id}.json"'
    return response


def dmz_import(request):
    from .forms import DMZImportForm
    if request.method == 'POST':
        form = DMZImportForm(request.POST)
        if form.is_valid():
            filename = form.cleaned_data['filename']
            dmz_dir = Path(__file__).parent.parent.parent.parent / 'dmz' / 'close_to_open'
            
            try:
                local_path = dmz_dir / filename
                if not local_path.exists():
                    messages.error(request, f'ファイルが見つかりません: {filename}')
                    return render(request, 'anonymizer_app/dmz_import.html', {'form': form})
                
                content = local_path.read_text(encoding='utf-8')
                # ローカルlogsフォルダーにコピー
                logs_dir = Path(__file__).parent / 'logs'
                logs_dir.mkdir(exist_ok=True)
                local_copy = logs_dir / filename
                local_copy.write_text(content, encoding='utf-8')
                
                messages.success(request, f'ファイルを取り込みました: {filename}')
                return render(request, 'anonymizer_app/dmz_import.html', {'form': DMZImportForm(), 'downloaded_path': str(local_copy)})
            except Exception as e:
                messages.error(request, f'ファイル取り込みに失敗しました: {e}')
                return render(request, 'anonymizer_app/dmz_import.html', {'form': form})
    else:
        form = DMZImportForm()
    return render(request, 'anonymizer_app/dmz_import.html', {'form': form})


def dmz_list(request):
    files = None
    dmz_dir = Path(__file__).parent.parent.parent.parent / 'dmz' / 'close_to_open'
    
    if request.method == 'POST':
        form = DMZListForm(request.POST)
        if form.is_valid():
            try:
                if not dmz_dir.exists():
                    messages.error(request, f'DMZディレクトリが見つかりません: {dmz_dir}')
                else:
                    entries = sorted(dmz_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
                    files = []
                    for entry in entries:
                        if entry.is_file():
                            stat = entry.stat()
                            modified = datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                            files.append({
                                'name': entry.name,
                                'size': stat.st_size,
                                'modified': modified,
                            })
            except Exception as e:
                messages.error(request, f'DMZ ファイル一覧の取得に失敗しました: {e}')
    else:
        form = DMZListForm()
        # GET時は自動で一覧を表示
        try:
            if dmz_dir.exists():
                entries = sorted(dmz_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
                files = []
                for entry in entries:
                    if entry.is_file():
                        stat = entry.stat()
                        modified = datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                        files.append({
                            'name': entry.name,
                            'size': stat.st_size,
                            'modified': modified,
                        })
        except Exception as e:
            messages.warning(request, f'DMZ ファイル一覧の取得に失敗: {e}')

    return render(request, 'anonymizer_app/dmz_list.html', {'form': form, 'files': files, 'dmz_path': str(dmz_dir)})


@require_http_methods(["GET", "POST"])
def dmz_export(request):
    # エクスポート: 保存済みの prompt_json をローカルDMZフォルダーに出力
    if request.method == 'POST':
        form = DMZExportForm(request.POST)
        if form.is_valid():
            source_id = form.cleaned_data.get('source_id')
            dmz_dir = Path(__file__).parent.parent.parent.parent / 'dmz' / 'close_to_open'

            try:
                if source_id:
                    metadata = RestoreMetadata.objects.filter(source_id=source_id).first()
                    if not metadata:
                        messages.error(request, f'source_id {source_id} が見つかりません')
                        return render(request, 'anonymizer_app/dmz_export.html', {'form': form})
                    payload = _sanitize_prompt_payload_for_dmz(metadata.prompt_json or {})
                    content = json.dumps(payload, ensure_ascii=False, indent=2)
                else:
                    messages.error(request, 'source_id を指定してください')
                    return render(request, 'anonymizer_app/dmz_export.html', {'form': form})

                # DMZディレクトリに出力
                dmz_dir.mkdir(parents=True, exist_ok=True)
                filename = f'prompt_{source_id}.json'
                output_path = dmz_dir / filename
                output_path.write_text(content, encoding='utf-8')
                
                messages.success(request, f'DMZへアップロードしました: {output_path}')
                return render(request, 'anonymizer_app/dmz_export.html', {'form': DMZExportForm(), 'uploaded_path': str(output_path)})
            except Exception as e:
                messages.error(request, f'アップロードに失敗しました: {e}')
                return render(request, 'anonymizer_app/dmz_export.html', {'form': form})
    else:
        initial = {}
        source_id = request.GET.get('source_id')
        if source_id:
            initial['source_id'] = source_id
        form = DMZExportForm(initial=initial)

    # GET: 保存されている source_id の一覧を渡す
    saved = RestoreMetadata.objects.all().order_by('-id')[:50]
    return render(request, 'anonymizer_app/dmz_export.html', {'form': form, 'saved': saved})


def prompts_list(request):
    prompts = Prompt.objects.all().order_by('-updated_at')
    return render(request, 'anonymizer_app/prompts_list.html', {'prompts': prompts})


def prompt_create(request):
    if request.method == 'POST':
        form = PromptForm(request.POST)
        if form.is_valid():
            Prompt.objects.create(
                name=form.cleaned_data['name'],
                content=form.cleaned_data['content']
            )
            return redirect('prompts_list')
    else:
        form = PromptForm()
    return render(request, 'anonymizer_app/prompt_form.html', {'form': form, 'create': True})


def prompt_edit(request, pk):
    prompt = get_object_or_404(Prompt, pk=pk)
    if request.method == 'POST':
        form = PromptForm(request.POST)
        if form.is_valid():
            prompt.name = form.cleaned_data['name']
            prompt.content = form.cleaned_data['content']
            prompt.save()
            return redirect('prompts_list')
    else:
        form = PromptForm(initial={'name': prompt.name, 'content': prompt.content})
    return render(request, 'anonymizer_app/prompt_form.html', {'form': form, 'create': False, 'prompt': prompt})


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
            messages.success(request, f'txtテンプレートを保存しました: {source.source_filename}')
            return redirect('templates_list')
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
            messages.success(request, f'txtテンプレートを更新しました: {source.source_filename}')
            return redirect('templates_list')
    else:
        source = None
        if tpl.source_filename:
            source = get_template_source_by_filename(tpl.source_filename)
        if source is None:
            source = get_template_source_by_name(tpl.name)
        form = TemplateForm(initial={
            'template_type': source.template_type if source else tpl.template_type,
            'name': source.name if source else tpl.name,
            'basic_content': source.basic_content if source else (tpl.basic_content or tpl.content),
            'additional_content': source.additional_content if source else tpl.additional_content,
        })
    return render(request, 'anonymizer_app/template_form.html', {'form': form, 'create': False, 'template': tpl})


def anonymization_rules(request):
    """Render the anonymization rules markdown as plain text for reference."""
    # prefer DB-stored rule if exists
    from .models import AnonymizationRule
    rule = AnonymizationRule.objects.order_by('-updated_at').first()
    if rule:
        text = rule.content
    else:
        rules_path = Path(__file__).resolve().parent / 'prompt_templates' / 'anonymization_rules.md'
        if rules_path.exists():
            text = rules_path.read_text(encoding='utf-8')
        else:
            return HttpResponse('匿名化ルールが見つかりません', status=404)

    try:
        import markdown
        html = markdown.markdown(text)
        return render(request, 'anonymizer_app/anonymization_rules.html', {'rules_html': html})
    except Exception:
        return render(request, 'anonymizer_app/anonymization_rules.html', {'rules_text': text})


def api_template_preview(request, template_name):
    """API endpoint to return template content as JSON for AJAX preview."""
    try:
        sync_templates_to_db()
        template = get_template_source_by_name(template_name)
        if template is None:
            return JsonResponse({'error': 'Template not found'}, status=404)
        return JsonResponse({
            'name': template.name,
            'template_type': template.template_type,
            'basic_content': template.basic_content or '',
            'additional_content': template.additional_content or '',
        })
    except Template.DoesNotExist:
        return JsonResponse({'error': 'Template not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def template_detail(request, template_name):
    """Display template details on a dedicated page."""
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
