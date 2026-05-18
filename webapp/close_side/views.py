import datetime
import difflib
import json
import uuid
from pathlib import Path

from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_http_methods

from anonymizer_app.forms import AnonymizeForm, DMZExportForm, PromptForm, TemplateForm
from anonymizer_app.models import AnonymizationRule, Prompt, RestoreMetadata, Template
from anonymizer_app.modules.anonymize import anonymize_text, build_prompt_payload
from anonymizer_app.template_defaults import load_default_template


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
                prompt_json=payload,
            )

            return render(request, 'anonymizer_app/result.html', {
                'form': form,
                'template_type': template_type,
                'text_items': text_items,
                'restore_map': restore_map,
                'restore_map_items': list(restore_map.items()),
                'prompt_json': json.dumps(payload, ensure_ascii=False, indent=2),
                'restore_json': json.dumps(restore_data, ensure_ascii=False, indent=2),
                'source_id': source_id,
            })
    else:
        form = AnonymizeForm()
    return render(request, 'anonymizer_app/index.html', {'form': form})


def download_prompt(request, source_id):
    metadata = get_object_or_404(RestoreMetadata, source_id=source_id)
    response = HttpResponse(
        json.dumps(metadata.prompt_json, ensure_ascii=False, indent=2),
        content_type='application/json',
    )
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


@require_http_methods(["GET", "POST"])
def dmz_export(request):
    if request.method == 'POST':
        form = DMZExportForm(request.POST)
        if form.is_valid():
            source_id = form.cleaned_data.get('source_id')
            dmz_dir = _close_to_open_dir()

            try:
                metadata = RestoreMetadata.objects.filter(source_id=source_id).first()
                if not metadata:
                    messages.error(request, f'source_id {source_id} が見つかりません')
                    return render(request, 'anonymizer_app/dmz_export.html', {'form': form})

                dmz_dir.mkdir(parents=True, exist_ok=True)
                filename = f'prompt_{source_id}.json'
                output_path = dmz_dir / filename
                output_path.write_text(
                    json.dumps(metadata.prompt_json, ensure_ascii=False, indent=2),
                    encoding='utf-8',
                )

                messages.success(request, f'OpenSide DMZ へ出力しました: {output_path}')
                return render(
                    request,
                    'anonymizer_app/dmz_export.html',
                    {'form': DMZExportForm(), 'uploaded_path': str(output_path)},
                )
            except Exception as e:
                messages.error(request, f'出力に失敗しました: {e}')
                return render(request, 'anonymizer_app/dmz_export.html', {'form': form})
    else:
        form = DMZExportForm(initial={'source_id': request.GET.get('source_id', '')})

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
                content=form.cleaned_data['content'],
            )
            return redirect('close_side:prompts_list')
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
            return redirect('close_side:prompts_list')
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
            return redirect('close_side:templates_list')
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
            return redirect('close_side:templates_list')
    else:
        form = TemplateForm(initial={
            'template_type': tpl.template_type,
            'name': tpl.name,
            'basic_content': tpl.basic_content or tpl.content,
            'additional_content': tpl.additional_content,
        })
    return render(request, 'anonymizer_app/template_form.html', {'form': form, 'create': False, 'template': tpl})


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
    try:
        template = Template.objects.get(name=template_name)
        return render(request, 'anonymizer_app/template_detail.html', {'template': template})
    except Template.DoesNotExist:
        return render(request, 'anonymizer_app/error.html', {'message': 'テンプレートが見つかりません'}, status=404)

