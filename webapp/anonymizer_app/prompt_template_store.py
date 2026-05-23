from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


TEMPLATE_DIR = Path(__file__).resolve().parent / 'prompt_templates'
DEFAULT_TEMPLATE_FILENAME = 'default.txt'


@dataclass(frozen=True)
class TemplateSpec:
    filename: str
    template_type: str
    name: str


@dataclass(frozen=True)
class TemplateSource:
    source_filename: str
    template_type: str
    name: str
    content: str
    basic_content: str
    additional_content: str


TEMPLATE_SPECS = [
    TemplateSpec('admission.txt', '入院時サマリー', '入院時サマリー（詳細版）'),
    TemplateSpec('psychiatric_admission.txt', '精神科入院時サマリー', '精神科入院時サマリー'),
    TemplateSpec('psychiatric_discharge_doctor.txt', '精神科退院時サマリー（医師用）', '精神科退院時サマリー（医師用）'),
    TemplateSpec('nursing_admission_summary.txt', '看護入院時サマリー', '看護入院時サマリー'),
    TemplateSpec('nursing_midterm_summary.txt', '看護中間サマリー', '看護中間サマリー'),
    TemplateSpec('nursing_discharge_summary.txt', '看護退院時サマリー', '看護退院時サマリー'),
    TemplateSpec('ot_evaluation_summary.txt', 'OT評価サマリー', 'OT評価サマリー'),
    TemplateSpec('psw_discharge_support_summary.txt', 'PSW退院支援サマリー', 'PSW退院支援サマリー'),
    TemplateSpec('psychiatric_home_nursing_summary.txt', '精神科訪問看護サマリー', '精神科訪問看護サマリー'),
    TemplateSpec('discharge.txt', '退院時サマリー', '退院時サマリー'),
    TemplateSpec('midterm.txt', '中間サマリー', '中間サマリー'),
    TemplateSpec('incident.txt', 'インシデントレポート', 'インシデントレポート（様式1-3）'),
    TemplateSpec('incident2.txt', 'インシデントレポート', 'インシデントレポート（簡易版）'),
    TemplateSpec('committee.txt', '委員会議事録', '委員会議事録'),
    TemplateSpec('nursing.txt', '看護計画', '看護計画'),
]

_SPECS_BY_FILENAME = {spec.filename: spec for spec in TEMPLATE_SPECS}


def _template_path(filename: str) -> Path:
    path = TEMPLATE_DIR / filename
    if path.name != filename or path.suffix != '.txt':
        raise ValueError(f'Invalid template filename: {filename}')
    return path


def load_default_template() -> str:
    path = _template_path(DEFAULT_TEMPLATE_FILENAME)
    if path.exists():
        return path.read_text(encoding='utf-8')
    return ''


def load_basic_template() -> str:
    return split_common_base(load_default_template())


def split_common_base(default_text: str) -> str:
    marker = 'あなたは医療文書作成支援AIです。'
    first = default_text.find(marker)
    if first == -1:
        return default_text.strip()

    second = default_text.find(marker, first + len(marker))
    if second == -1:
        return default_text.strip()
    return default_text[:second].strip()


def extract_additional_content(full_text: str, common_base: str) -> str:
    normalized = full_text.strip()
    if normalized.startswith(common_base):
        return normalized[len(common_base):].strip()
    return normalized


def _parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith('---\n'):
        return {}, text

    end = text.find('\n---\n', 4)
    if end == -1:
        return {}, text

    metadata: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ':' not in line:
            continue
        key, value = line.split(':', 1)
        metadata[key.strip()] = value.strip()

    return metadata, text[end + len('\n---\n'):]


def _format_front_matter(template_type: str, name: str, body: str) -> str:
    return f'---\ntemplate_type: {template_type}\nname: {name}\n---\n{body.strip()}\n'


def _content_from_parts(basic_content: str, additional_content: str) -> str:
    basic = (basic_content or '').strip()
    additional = (additional_content or '').strip()
    if additional:
        return f'{basic}\n\n{additional}'.strip()
    return basic


def _source_from_file(path: Path, basic_content: str) -> TemplateSource:
    text = path.read_text(encoding='utf-8')
    metadata, body = _parse_front_matter(text)
    spec = _SPECS_BY_FILENAME.get(path.name)

    template_type = metadata.get('template_type') or (spec.template_type if spec else path.stem)
    name = metadata.get('name') or (spec.name if spec else path.stem)
    additional_content = extract_additional_content(body, basic_content)
    content = _content_from_parts(basic_content, additional_content)

    return TemplateSource(
        source_filename=path.name,
        template_type=template_type,
        name=name,
        content=content,
        basic_content=basic_content,
        additional_content=additional_content,
    )


def list_template_sources() -> list[TemplateSource]:
    basic_content = split_common_base(load_default_template())
    sources: list[TemplateSource] = []
    seen: set[str] = set()

    for spec in TEMPLATE_SPECS:
        path = _template_path(spec.filename)
        if path.exists():
            sources.append(_source_from_file(path, basic_content))
            seen.add(path.name)

    for path in sorted(TEMPLATE_DIR.glob('*.txt')):
        if path.name == DEFAULT_TEMPLATE_FILENAME or path.name in seen:
            continue
        sources.append(_source_from_file(path, basic_content))

    return sources


def get_template_source_by_name(name: str) -> TemplateSource | None:
    for source in list_template_sources():
        if source.name == name:
            return source
    return None


def get_template_source_by_filename(filename: str) -> TemplateSource | None:
    path = _template_path(filename)
    if not path.exists():
        return None
    return _source_from_file(path, split_common_base(load_default_template()))


def _make_template_filename(name: str) -> str:
    digest = hashlib.sha1(name.encode('utf-8')).hexdigest()[:8]
    return f'template_{digest}.txt'


def _available_template_filename(name: str) -> str:
    base = _make_template_filename(name)
    path = _template_path(base)
    if not path.exists():
        return base

    stem = path.stem
    for index in range(2, 100):
        candidate = f'{stem}_{index}.txt'
        if not _template_path(candidate).exists():
            return candidate

    raise ValueError('Too many templates with the same generated filename')


def write_template_source(
    *,
    source_filename: str | None,
    template_type: str,
    name: str,
    basic_content: str,
    additional_content: str,
) -> TemplateSource:
    filename = source_filename or _available_template_filename(name)
    path = _template_path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)

    body = _content_from_parts(basic_content, additional_content)
    spec = _SPECS_BY_FILENAME.get(filename)
    if spec and spec.template_type == template_type and spec.name == name:
        text = f'{body.strip()}\n'
    else:
        text = _format_front_matter(template_type, name, body)

    path.write_text(text, encoding='utf-8')
    source = get_template_source_by_filename(filename)
    if source is None:
        raise FileNotFoundError(f'Written template was not found: {filename}')
    return source


def delete_template_source(source_filename: str) -> None:
    if not source_filename:
        return
    if source_filename == DEFAULT_TEMPLATE_FILENAME:
        raise ValueError('共通テンプレートは削除できません')

    path = _template_path(source_filename)
    if path.exists():
        path.unlink()


def sync_templates_to_db(*, prune_stale: bool = False) -> dict[str, object]:
    from .models import Template

    sources = list_template_sources()
    created_count = 0
    updated_count = 0
    templates = []

    for source in sources:
        template = Template.objects.filter(source_filename=source.source_filename).first()
        if template is None:
            template = Template.objects.filter(name=source.name).order_by('id').first()

        defaults = {
            'template_type': source.template_type,
            'name': source.name,
            'content': source.content,
            'basic_content': source.basic_content,
            'additional_content': source.additional_content,
            'source_filename': source.source_filename,
        }

        if template is None:
            template = Template.objects.create(**defaults)
            created_count += 1
        else:
            changed = False
            for field, value in defaults.items():
                if getattr(template, field) != value:
                    setattr(template, field, value)
                    changed = True
            if changed:
                template.save()
                updated_count += 1

        templates.append(template)

    if prune_stale:
        filenames = [source.source_filename for source in sources]
        Template.objects.exclude(source_filename__in=filenames).delete()

    return {
        'created': created_count,
        'updated': updated_count,
        'templates': templates,
    }
