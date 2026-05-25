import difflib
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from .loader import load_config
from .utils import write_json


@dataclass
class AnonymizationResult:
    text: str
    restore_map: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


PREFERRED_PERSON_SENTINEL = '__PREFERRED_PATIENT_PERSON__'


def replace_patterns(text: str, patterns, label_prefix, restore_map):
    result = text
    for pattern in patterns:
        for match in re.finditer(pattern, result):
            token = match.group(0)
            if token in restore_map:
                continue
            label = f"{label_prefix}_{len(restore_map) + 1}"
            restore_map[label] = token
            result = result.replace(token, label, 1)
    return result


def normalize_fullwidth_text(text: str, restore_map: dict) -> str:
    # 全角英数字およびよく使われる全角記号を半角に変換
    fullwidth = (
        '０１２３４５６７８９'
        'ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ'
        'ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ'
        '：－，．（）'
    )
    ascii_replacements = (
        '0123456789'
        'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        'abcdefghijklmnopqrstuvwxyz'
        ':-,.'
        '()'
    )
    translation = {ord(fw): ord(ascii_) for fw, ascii_ in zip(fullwidth, ascii_replacements)}
    normalized = text.translate(translation)

    # 変換前後の差分を記録し、復元時に元文字列を再構築できるようにする
    matcher = difflib.SequenceMatcher(None, text, normalized)
    # 全角英数字から半角英数字への変換は、復元時に元の全角に戻さず
    # 半角のまま使いたいという要件があるため、その差分は復元マップへ記録しない。
    # それ以外の差分は記録して復元できるようにする。
    fullwidth_alnum = (
        '０１２３４５６７８９'
        'ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ'
        'ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ'
    )
    fullwidth_alnum_set = set(fullwidth_alnum)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'replace':
            original_segment = text[i1:i2]
            anonymized_segment = normalized[j1:j2]
            # 元のセグメントに全角英数字が含まれる場合は、復元マップに登録しない
            if any(ch in fullwidth_alnum_set for ch in original_segment):
                continue
            record_restore_segment(restore_map, anonymized_segment, original_segment)

    return normalized


def record_restore_segment(restore_map: dict, anonymized_value: str, original_value: str):
    if not anonymized_value or anonymized_value == original_value:
        return
    if anonymized_value in restore_map:
        return
    restore_map[anonymized_value] = original_value


def unique_restore_label(restore_map: dict, base_label: str) -> str:
    if base_label not in restore_map:
        return base_label

    index = 2
    while f'{base_label}_{index}' in restore_map:
        index += 1
    return f'{base_label}_{index}'


def generalize_date_text(text: str, restore_map: dict) -> str:
    def replace_date(match):
        year = match.group('year') or ''
        month = int(match.group('month'))
        day = int(match.group('day'))
        anonymized = f'{year}{month}月'
        if day <= 10:
            anonymized += '上旬'
        elif day <= 20:
            anonymized += '中旬'
        else:
            anonymized += '下旬'
        record_restore_segment(restore_map, anonymized, match.group(0))
        return anonymized

    date_pattern = re.compile(r'(?P<year>(?:平成|昭和|令和)?\d{1,4}年)?(?P<month>\d{1,2})月(?P<day>\d{1,2})日')
    return date_pattern.sub(replace_date, text)


def generalize_time_text(text: str, restore_map: dict) -> str:
    time_index = 0

    def anonymized_time_label(period: str, original: str) -> str:
        nonlocal time_index
        time_index += 1
        label = unique_restore_label(restore_map, f'{period}(時刻{time_index})')
        record_restore_segment(restore_map, label, original)
        return label

    def replace_time(match):
        hour_text = match.group('colon_hour') or match.group('jp_hour')
        hour = int(hour_text)
        period = match.group('period')
        if not period:
            period = '午前' if hour < 12 else '午後'
        return anonymized_time_label(period, match.group(0))

    time_pattern = re.compile(
        r'(?P<colon_hour>\d{1,2})[:：]\d{1,2}'
        r'|(?<!\d)(?P<period>午前|午後)?(?P<jp_hour>\d{1,2})時(?:\d{1,2}分)?'
    )
    return time_pattern.sub(replace_time, text)


def record_time_restore(match, restore_map: dict, label_factory=None) -> str:
    original = match.group(0)
    anonymized = '午前' if '午前' in original else '午後'
    if label_factory:
        return label_factory(anonymized, original)
    record_restore_segment(restore_map, anonymized, original)
    return anonymized


def simplify_address(address: str) -> str:
    pref_city_match = re.search(r'([一-龥]+[都道府県])([一-龥]+市)', address)
    if pref_city_match:
        return f'{pref_city_match.group(1)}{pref_city_match.group(2)}内'
    city_match = re.search(r'([一-龥]+市)', address)
    if city_match:
        return f'{city_match.group(1)}内'
    ward_match = re.search(r'([一-龥]+区)', address)
    if ward_match:
        return f'{ward_match.group(1)}内'
    return '住所'


def generalize_address_text(text: str, restore_map: dict) -> str:
    def replace_address(match):
        address = match.group(0)
        anonymized = simplify_address(address)
        record_restore_segment(restore_map, anonymized, address)
        return anonymized

    address_pattern = re.compile(r'([一-龥]+[都道府県][一-龥]+市.*?)(?=に住む|に居住|に在住|、|。|$)')
    return address_pattern.sub(replace_address, text)


def normalize_whitespace(text: str) -> str:
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\s+([、。()])', r'\1', text)
    text = re.sub(r'([、。])\s+', r'\1', text)
    text = re.sub(r'(?<=[\u3040-\u30ff\u4e00-\u9fff]) (?=[\u3040-\u30ff\u4e00-\u9fff])', '', text)
    return text.strip()


def anonymize_person_names(text: str, restore_map: dict) -> str:
    name_map = {}
    patient_index = 0

    def replace_name(match):
        nonlocal patient_index
        original = match.group(0)
        if original in name_map:
            return name_map[original]

        label = f'患者{chr(ord("A") + patient_index)}'
        if original.endswith('氏'):
            label += '氏'
        elif original.endswith('さん'):
            label += 'さん'
        patient_index += 1
        name_map[original] = label
        restore_map[label] = original
        return label

    patterns = [r'患者[一-龥]{2,3}(?:氏|さん)?', r'[一-龥]{2,4}氏', r'[一-龥]{2,4}さん']
    for pattern in patterns:
        text = re.sub(pattern, replace_name, text)
    return text


def _normalize_preferred_person_names(preferred_person_names) -> list[str]:
    if not preferred_person_names:
        return []

    if isinstance(preferred_person_names, str):
        candidates = [preferred_person_names]
    else:
        candidates = list(preferred_person_names)

    normalized: list[str] = []
    for candidate in candidates:
        text = str(candidate or '').strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def anonymize_text(
    text: str,
    template_type: str = 'generic',
    *,
    preferred_person_names=None,
    preferred_person_label: str = '患者本人A',
    preferred_person_original: str = '',
) -> AnonymizationResult:
    config = load_config(Path(__file__).resolve().parents[1] / 'config')
    restore_map = {}
    working_text = text
    preferred_names = _normalize_preferred_person_names(preferred_person_names)
    for preferred_name in sorted(preferred_names, key=len, reverse=True):
        working_text = working_text.replace(preferred_name, PREFERRED_PERSON_SENTINEL)

    anonymized = normalize_fullwidth_text(working_text, restore_map)

    anonymized = generalize_date_text(anonymized, restore_map)
    anonymized = generalize_time_text(anonymized, restore_map)
    anonymized = generalize_address_text(anonymized, restore_map)
    anonymized = anonymize_person_names(anonymized, restore_map)
    if PREFERRED_PERSON_SENTINEL in anonymized:
        anonymized = anonymized.replace(PREFERRED_PERSON_SENTINEL, preferred_person_label)
        if preferred_person_original:
            restore_map[preferred_person_label] = preferred_person_original
        elif preferred_names:
            restore_map[preferred_person_label] = preferred_names[0]
    anonymized = normalize_whitespace(anonymized)

    entity_replacements = config.get('entity_replacements', [])

    for item in entity_replacements:
        term = item.get('term')
        category = item.get('category')
        if term and category and term in anonymized:
            label = f"{category.replace(' ', '_').upper()}_{len(restore_map) + 1}"
            restore_map[label] = term
            anonymized = anonymized.replace(term, label)

    metadata = {
        'template_type': template_type,
        'anonymized_at': None,
        'hash_id': str(uuid.uuid4())
    }
    return AnonymizationResult(text=anonymized, restore_map=restore_map, metadata=metadata)


def restore_text(anonymized_text: str, restore_map: dict) -> str:
    restored = anonymized_text
    for anonymized, original in sorted(restore_map.items(), key=lambda item: len(item[0]), reverse=True):
        if anonymized:
            restored = restored.replace(anonymized, original)
    return restored


def build_prompt_payload(
    template_type: str,
    content: dict,
    source_id: str,
    title: str | None = None,
    patient_profile: dict | None = None,
):
    prompt_text = create_prompt_text(
        template_type,
        content,
        source_id=source_id,
        title=title,
        patient_profile=patient_profile,
    )
    payload = {
        'id': source_id,
        'template_type': template_type,
        'title': title,
        'prompt': prompt_text,
        'prompt_text': prompt_text,
        'content': content,
        'metadata': {
            'source_id': source_id,
            'created_at': None,
        },
    }
    if title:
        payload['metadata']['title'] = title
    return payload


def _render_patient_context_block(patient_profile: dict | None) -> str:
    if not isinstance(patient_profile, dict):
        return ''

    anonymized_patient_id = str(
        patient_profile.get('anonymized_patient_id')
        or patient_profile.get('patient_id')
        or ''
    ).strip()
    birth_date = str(
        patient_profile.get('birth_date_display')
        or patient_profile.get('birth_date')
        or ''
    ).strip()
    sex = str(
        patient_profile.get('sex_display')
        or patient_profile.get('sex')
        or ''
    ).strip()
    primary_diagnosis = str(patient_profile.get('primary_diagnosis') or '').strip()

    lines: list[str] = []
    if anonymized_patient_id:
        lines.append(f'・匿名ID: {anonymized_patient_id}')
    if sex:
        lines.append(f'・性別: {sex}')
    if birth_date:
        lines.append(f'・生年月日: {birth_date}')
    if primary_diagnosis:
        lines.append(f'・主病名: {primary_diagnosis}')

    if not lines:
        return ''

    return '【患者情報】\n' + '\n'.join(lines)


def build_result_payload(
    source_id: str,
    result_text: str,
    reviewer: str = 'unknown',
    anonymized_patient_id: str = '',
):
    payload = {}
    anonymized_patient_id = str(anonymized_patient_id or '').strip()
    if anonymized_patient_id:
        payload['anonymized_patient_id'] = anonymized_patient_id
    payload['id'] = f'result_{source_id}'
    payload['source_id'] = source_id
    payload['result_text'] = result_text
    payload['metadata'] = {
        'processed_at': None,
        'reviewer': reviewer,
    }
    return payload


def _parse_template_front_matter(text: str) -> str:
    if not text.startswith('---\n'):
        return text

    end = text.find('\n---\n', 4)
    if end == -1:
        return text
    return text[end + len('\n---\n'):]


def _template_file_candidates(template_type: str) -> list[str]:
    by_name = {
        '入院時サマリー': 'admission.txt',
        '入院時サマリー（詳細版）': 'admission.txt',
        '精神科入院時サマリー': 'psychiatric_admission.txt',
        '退院時サマリー': 'discharge.txt',
        '中間サマリー': 'midterm.txt',
        'インシデントレポート': 'incident.txt',
        'インシデントレポート（様式1-3）': 'incident.txt',
        'インシデントレポート（簡易版）': 'incident2.txt',
        '委員会議事録': 'committee.txt',
        '看護計画': 'nursing.txt',
    }
    filenames = []
    if template_type in by_name:
        filenames.append(by_name[template_type])
    filenames.append('default.txt')
    return filenames


def _load_prompt_template_text(template_type: str) -> str | None:
    try:
        from anonymizer_app.prompt_template_store import get_template_source_by_name

        source = get_template_source_by_name(template_type)
        if source:
            return source.content
    except Exception:
        pass

    template_dir = Path(__file__).resolve().parents[2] / 'webapp' / 'anonymizer_app' / 'prompt_templates'
    for filename in _template_file_candidates(template_type):
        path = template_dir / filename
        if path.exists():
            return _parse_template_front_matter(path.read_text(encoding='utf-8')).strip()
    return None


def _render_prompt_template(
    template_text: str,
    template_type: str,
    content: dict,
    source_id: str | None,
    title: str | None,
    patient_profile: dict | None = None,
) -> str:
    anonymized_text = content.get('anonymized_text') or content.get('text') or ''
    patient_context = _render_patient_context_block(patient_profile)
    values = {
        'request_no': content.get('request_no') or source_id or '',
        'document_type': content.get('document_type') or template_type,
        'anonymized_text': anonymized_text,
        'source_id': source_id or '',
        'title': title or '',
        'text': anonymized_text,
        'patient_context': patient_context,
    }
    values.update({key: value for key, value in content.items() if isinstance(key, str)})

    rendered = template_text
    for key, value in values.items():
        rendered = rendered.replace(f'{{{key}}}', '' if value is None else str(value))
    rendered = rendered.strip()
    if patient_context:
        return f'{patient_context}\n\n{rendered}'
    return rendered


def create_prompt_text(
    template_type: str,
    content: dict,
    source_id: str | None = None,
    title: str | None = None,
    patient_profile: dict | None = None,
) -> str:
    template_text = _load_prompt_template_text(template_type)
    if template_text:
        return _render_prompt_template(
            template_text,
            template_type,
            content,
            source_id,
            title,
            patient_profile=patient_profile,
        )

    lines = [f'あなたは精神科病棟の看護師です。以下の匿名化された情報をもとに、{template_type}を作成してください。', '']
    patient_context = _render_patient_context_block(patient_profile)
    if patient_context:
        lines.extend([patient_context, ''])
    for key, value in content.items():
        label = '入力本文' if key == 'text' else key
        lines.append(f'【{label}】')
        lines.append(value)
        lines.append('')
    lines.append('上記の匿名化された入力テキストをテンプレートの最後に追加してください。')
    lines.append('')
    lines.append('出力形式：')
    lines.append('1. 本文')
    lines.append('2. 箇条書き')
    return '\n'.join(lines)
