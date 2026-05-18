import difflib
import json
import uuid
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse
from django.utils.html import escape
from django.utils.safestring import mark_safe
from .forms import AnonymizeForm
from .models import RestoreMetadata, Prompt, Template
from .forms import PromptForm, TemplateForm
from anonymizer_app.modules.anonymize import anonymize_text, build_prompt_payload
from .template_defaults import load_default_template
import os
from django.contrib import messages
from pathlib import Path

try:
    import paramiko
except Exception:
    paramiko = None
from django.views.decorators.http import require_http_methods
from .forms import DMZExportForm, DMZImportForm
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
    payload = metadata.prompt_json
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
            host = form.cleaned_data['host']
            port = form.cleaned_data.get('port') or 22
            username = form.cleaned_data['username']
            password = form.cleaned_data.get('password') or None
            remote_path = form.cleaned_data['remote_path']
            target_filename = form.cleaned_data.get('target_filename') or os.path.basename(remote_path)

            if paramiko is None:
                messages.error(request, 'paramikoがインストールされていません。requirements.txtを更新してください。')
                return render(request, 'anonymizer_app/dmz_import.html', {'form': form})

            try:
                transport = paramiko.Transport((host, int(port)))
                transport.connect(username=username, password=password)
                sftp = paramiko.SFTPClient.from_transport(transport)
                local_dir = os.path.join(os.path.dirname(__file__), 'logs')
                local_dir = os.path.normpath(local_dir)
                os.makedirs(local_dir, exist_ok=True)
                local_path = os.path.join(local_dir, target_filename)
                sftp.get(remote_path, local_path)
                sftp.close()
                transport.close()
                messages.success(request, f'ファイルを取り込みました: {local_path}')
                return render(request, 'anonymizer_app/dmz_import.html', {'form': DMZImportForm(), 'downloaded_path': local_path})
            except Exception as e:
                messages.error(request, f'ファイル取り込みに失敗しました: {e}')
                return render(request, 'anonymizer_app/dmz_import.html', {'form': form})
    else:
        form = DMZImportForm()
    return render(request, 'anonymizer_app/dmz_import.html', {'form': form})


@require_http_methods(["GET", "POST"])
def dmz_export(request):
    # エクスポート: 保存済みの prompt_json を DMZ の指定パスにアップロードする
    if request.method == 'POST':
        form = DMZExportForm(request.POST)
        if form.is_valid():
            host = form.cleaned_data['host']
            port = form.cleaned_data.get('port') or 22
            username = form.cleaned_data['username']
            password = form.cleaned_data.get('password') or None
            remote_path = form.cleaned_data['remote_path']
            source_id = form.cleaned_data.get('source_id') or None

            if paramiko is None:
                messages.error(request, 'paramikoがインストールされていません。requirements.txtを更新してください。')
                return render(request, 'anonymizer_app/dmz_export.html', {'form': form})

            try:
                # 送信データを準備
                if source_id:
                    metadata = RestoreMetadata.objects.filter(source_id=source_id).first()
                    if not metadata:
                        messages.error(request, f'source_id {source_id} が見つかりません')
                        return render(request, 'anonymizer_app/dmz_export.html', {'form': form})
                    payload = metadata.prompt_json
                    content = json.dumps(payload, ensure_ascii=False, indent=2)
                else:
                    messages.error(request, 'source_id を指定してください')
                    return render(request, 'anonymizer_app/dmz_export.html', {'form': form})

                # 一時ファイルに書き出してSFTPでアップロード
                tmp_path = os.path.join('/tmp', f'export_{uuid.uuid4().hex}.json')
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    f.write(content)

                transport = paramiko.Transport((host, int(port)))
                transport.connect(username=username, password=password)
                sftp = paramiko.SFTPClient.from_transport(transport)
                # リモートディレクトリがない場合はエラーになるため、単純にputする
                sftp.put(tmp_path, remote_path)
                sftp.close()
                transport.close()
                os.remove(tmp_path)
                messages.success(request, f'DMZへアップロードしました: {remote_path}')
                return render(request, 'anonymizer_app/dmz_export.html', {'form': DMZExportForm(), 'uploaded_path': remote_path})
            except Exception as e:
                messages.error(request, f'アップロードに失敗しました: {e}')
                return render(request, 'anonymizer_app/dmz_export.html', {'form': form})
    else:
        form = DMZExportForm()

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
    templates = Template.objects.all().order_by('template_type', '-updated_at')
    return render(request, 'anonymizer_app/templates_list.html', {'templates': templates})


def template_create(request):
    if request.method == 'POST':
        form = TemplateForm(request.POST)
        if form.is_valid():
            basic = form.cleaned_data.get('basic_content') or ''
            additional = form.cleaned_data.get('additional_content') or ''
            content = f"{basic}\n\n{additional}" if additional else basic
            Template.objects.create(
                template_type=form.cleaned_data['template_type'],
                name=form.cleaned_data['name'],
                content=content,
                basic_content=basic,
                additional_content=additional,
            )
            return redirect('templates_list')
    else:
        form = TemplateForm(initial={'basic_content': load_default_template()})
    return render(request, 'anonymizer_app/template_form.html', {'form': form, 'create': True})


def template_edit(request, pk):
    tpl = get_object_or_404(Template, pk=pk)
    if request.method == 'POST':
        form = TemplateForm(request.POST)
        if form.is_valid():
            basic = form.cleaned_data.get('basic_content') or ''
            additional = form.cleaned_data.get('additional_content') or ''
            tpl.template_type = form.cleaned_data['template_type']
            tpl.name = form.cleaned_data['name']
            tpl.basic_content = basic
            tpl.additional_content = additional
            tpl.content = f"{basic}\n\n{additional}" if additional else basic
            tpl.save()
            return redirect('templates_list')
    else:
        form = TemplateForm(initial={
            'template_type': tpl.template_type,
            'name': tpl.name,
            'basic_content': tpl.basic_content or tpl.content,
            'additional_content': tpl.additional_content,
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
        template = Template.objects.get(name=template_name)
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
        template = Template.objects.get(name=template_name)
        return render(request, 'anonymizer_app/template_detail.html', {'template': template})
    except Template.DoesNotExist:
        return render(request, 'anonymizer_app/error.html', {'message': 'テンプレートが見つかりません'}, status=404)
