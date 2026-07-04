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
PREFERRED_ENTITY_SENTINEL_PREFIX = '__PREFERRED_ENTITY_'


DEFAULT_NAME_PATTERNS = [
    r'患者[一-龥]{2,3}(?:[ 　][一-龥]{1,4})?(?:氏|さん)?',
    r'[一-龥]{1,4}[ 　][一-龥]{1,4}(?:氏|さん)',
    r'[一-龥]{2,4}氏',
    r'[一-龥]{2,4}さん',
]

DEFAULT_ADDRESS_PATTERNS = [
    r'(?:住所[:：]?\s*)?(?:北海道|[一-龥]{1,3}[都道府県])[一-龥ァ-ヶー0-9\-]+?(?:市|区|町|村)[一-龥ァ-ヶー0-9\-]*?(?=に住む|に居住|に在住|、|。|$)',
    r'(?:住所[:：]?\s*)?[一-龥ァ-ヶー0-9\-]+?(?:市|区|町|村)[一-龥ァ-ヶー0-9\-]*?(?=に住む|に居住|に在住|、|。|$)',
]

DEFAULT_DATE_PATTERNS = [
    r'(?P<year>(?:平成|昭和|令和)\d{1,4}|令和元|\d{4})年(?P<month>\d{1,2})月(?P<day>\d{1,2})日',
    r'(?P<year>\d{4})[/-](?P<month>\d{1,2})[/-](?P<day>\d{1,2})',
    r'(?<!\d)(?P<month>\d{1,2})月(?P<day>\d{1,2})日',
]

DEFAULT_TIME_PATTERNS = [
    r'(?P<period>午前|午後)?(?P<hour>\d{1,2})[:：](?P<minute>\d{1,2})(?:分)?(?:頃)?',
    r'(?P<period>午前|午後)?(?P<hour>\d{1,2})時(?:(?P<minute>\d{1,2})分)?(?:頃)?',
]

DEFAULT_AGE_PATTERNS = [
    r'(?<!\d)\d{1,3}(?:歳|才)(?!\d)',
]

DEFAULT_PHONE_PATTERNS = [
    r'(?:電話(?:番号)?[:：]?\s*)?(?:\+?81[-\s]?)?0\d{1,4}[-‐‑‒–—―ー－\s]?\d{1,4}[-‐‑‒–—―ー－\s]?\d{4}',
]

DEFAULT_EMAIL_PATTERNS = [
    r'(?:メール(?:アドレス)?[:：]?\s*)?[A-Za-z0-9._%+-]+[＠@][A-Za-z0-9.-]+\.[A-Za-z]{2,}',
]

DEFAULT_ID_PATTERNS = [
    r'(?:患者ID|患者番号|カルテ番号|診察券番号|受付番号)[:：]?\s*[A-Za-z0-9\-]{3,}',
]

DEFAULT_ROOM_PATTERNS = [
    r'(?<!\d)\d{1,4}号室(?!\d)',
]


def _compile_patterns(patterns, flags: int = 0):
    compiled = []
    for pattern in patterns or []:
        if not pattern:
            continue
        if hasattr(pattern, 'sub') and hasattr(pattern, 'finditer'):
            compiled.append(pattern)
        else:
            compiled.append(re.compile(pattern, flags))
    return compiled


def _configured_patterns(config: dict, key: str, fallback_patterns, *, flags: int = 0):
    patterns = config.get(key)
    if not patterns:
        patterns = fallback_patterns
    if isinstance(patterns, str):
        patterns = [patterns]
    return _compile_patterns(patterns, flags=flags)


def replace_patterns(text: str, patterns, label_prefix, restore_map):
    result = text
    original_to_label: dict[str, str] = {}
    counter = 0
    for pattern in _compile_patterns(patterns):
        def repl(match):
            nonlocal counter
            original = match.group(0)
            if original in original_to_label:
                return original_to_label[original]

            counter += 1
            base_label = f'{label_prefix}{counter}'
            label = unique_restore_label(restore_map, base_label)
            restore_map[label] = original
            original_to_label[original] = label
            return label

        result = pattern.sub(repl, result)
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


def _format_year_text(year_text: str) -> str:
    year_text = str(year_text or '').strip()
    if not year_text:
        return ''
    if year_text.endswith('年'):
        return year_text
    return f'{year_text}年'


def generalize_date_text(text: str, restore_map: dict, patterns=None) -> str:
    def replace_date(match):
        year = _format_year_text(match.groupdict().get('year') or '')
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

    date_patterns = _compile_patterns(patterns or DEFAULT_DATE_PATTERNS)
    for pattern in date_patterns:
        text = pattern.sub(replace_date, text)
    return text


def generalize_time_text(text: str, restore_map: dict, patterns=None) -> str:
    time_index = 0

    def anonymized_time_label(period: str, original: str) -> str:
        nonlocal time_index
        time_index += 1
        label = unique_restore_label(restore_map, f'{period}(時刻{time_index})')
        record_restore_segment(restore_map, label, original)
        return label

    def replace_time(match):
        hour_text = match.groupdict().get('hour')
        hour = int(hour_text)
        period = match.groupdict().get('period')
        if not period:
            period = '午前' if hour < 12 else '午後'
        return anonymized_time_label(period, match.group(0))

    time_patterns = _compile_patterns(patterns or DEFAULT_TIME_PATTERNS)
    for pattern in time_patterns:
        text = pattern.sub(replace_time, text)
    return text


def record_time_restore(match, restore_map: dict, label_factory=None) -> str:
    original = match.group(0)
    anonymized = '午前' if '午前' in original else '午後'
    if label_factory:
        return label_factory(anonymized, original)
    record_restore_segment(restore_map, anonymized, original)
    return anonymized


def simplify_address(address: str) -> str:
    pref_city_match = re.search(r'((?:北海道|[一-龥]{1,3}[都道府県]))([一-龥ァ-ヶー0-9\-]+?(?:市|区|町|村))', address)
    if pref_city_match:
        return f'{pref_city_match.group(1)}{pref_city_match.group(2)}内'
    municipality_match = re.search(r'([一-龥ァ-ヶー0-9\-]+?(?:市|区|町|村))', address)
    if municipality_match:
        return f'{municipality_match.group(1)}内'
    return '住所'


def generalize_address_text(text: str, restore_map: dict, patterns=None) -> str:
    def replace_address(match):
        address = match.group(0)
        anonymized = simplify_address(address)
        record_restore_segment(restore_map, anonymized, address)
        return anonymized

    address_patterns = _compile_patterns(patterns or DEFAULT_ADDRESS_PATTERNS)
    for pattern in address_patterns:
        text = pattern.sub(replace_address, text)
    return text


def generalize_age_text(text: str, restore_map: dict, patterns=None) -> str:
    age_patterns = _compile_patterns(patterns or DEFAULT_AGE_PATTERNS)
    return replace_patterns(text, age_patterns, '年齢', restore_map)


def anonymize_contact_text(text: str, restore_map: dict, config: dict) -> str:
    text = replace_patterns(
        text,
        _configured_patterns(config, 'phone_patterns', DEFAULT_PHONE_PATTERNS, flags=re.IGNORECASE),
        '電話番号',
        restore_map,
    )
    text = replace_patterns(
        text,
        _configured_patterns(config, 'email_patterns', DEFAULT_EMAIL_PATTERNS, flags=re.IGNORECASE),
        'メール',
        restore_map,
    )
    text = replace_patterns(
        text,
        _configured_patterns(config, 'id_patterns', DEFAULT_ID_PATTERNS, flags=re.IGNORECASE),
        '患者ID',
        restore_map,
    )
    text = replace_patterns(
        text,
        _configured_patterns(config, 'room_patterns', DEFAULT_ROOM_PATTERNS, flags=re.IGNORECASE),
        '病室',
        restore_map,
    )
    return text


def normalize_whitespace(text: str) -> str:
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\s+([、。()])', r'\1', text)
    text = re.sub(r'([、。])\s+', r'\1', text)
    text = re.sub(r'(?<=[\u3040-\u30ff\u4e00-\u9fff]) (?=[\u3040-\u30ff\u4e00-\u9fff])', '', text)
    return text.strip()


def _alphabet_label(index: int) -> str:
    index += 1
    letters = []
    while index:
        index, remainder = divmod(index - 1, 26)
        letters.append(chr(ord('A') + remainder))
    return ''.join(reversed(letters))


def anonymize_person_names(text: str, restore_map: dict, patterns=None) -> str:
    name_map = {}
    patient_index = 0

    def replace_name(match):
        nonlocal patient_index
        original = match.group(0)
        if original in name_map:
            return name_map[original]

        label = f'患者{_alphabet_label(patient_index)}'
        if original.endswith('氏'):
            label += '氏'
        elif original.endswith('さん'):
            label += 'さん'
        patient_index += 1
        name_map[original] = label
        restore_map[label] = original
        return label

    for pattern in _compile_patterns(patterns or DEFAULT_NAME_PATTERNS):
        text = pattern.sub(replace_name, text)
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


def _normalize_preferred_entity_groups(
    preferred_entity_groups=None,
    *,
    preferred_person_names=None,
    preferred_person_label: str = '患者本人A',
    preferred_person_original: str = '',
) -> list[dict[str, object]]:
    if preferred_entity_groups:
        if isinstance(preferred_entity_groups, dict):
            candidates = [preferred_entity_groups]
        else:
            candidates = list(preferred_entity_groups)

        normalized_groups: list[dict[str, object]] = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            names = candidate.get('names') or candidate.get('preferred_person_names') or []
            label = str(candidate.get('label') or candidate.get('preferred_person_label') or '').strip()
            original = str(candidate.get('original') or candidate.get('preferred_person_original') or '').strip()
            normalized_names = _normalize_preferred_person_names(names)
            if not label or not normalized_names:
                continue
            normalized_groups.append({
                'label': label,
                'names': normalized_names,
                'original': original or normalized_names[0],
            })
        return normalized_groups

    normalized_names = _normalize_preferred_person_names(preferred_person_names)
    if not normalized_names:
        return []
    return [{
        'label': preferred_person_label,
        'names': normalized_names,
        'original': preferred_person_original or normalized_names[0],
    }]


def anonymize_text(
    text: str,
    template_type: str = 'generic',
    *,
    preferred_entity_groups=None,
    preferred_person_names=None,
    preferred_person_label: str = '患者本人A',
    preferred_person_original: str = '',
) -> AnonymizationResult:
    config = load_config(Path(__file__).resolve().parents[1] / 'config')
    restore_map = {}
    working_text = text
    preferred_groups = _normalize_preferred_entity_groups(
        preferred_entity_groups,
        preferred_person_names=preferred_person_names,
        preferred_person_label=preferred_person_label,
        preferred_person_original=preferred_person_original,
    )
    if preferred_groups:
        group_sentinels: list[tuple[str, dict[str, object]]] = []
        preferred_replacements: list[tuple[str, str, dict[str, object]]] = []
        for index, group in enumerate(preferred_groups):
            sentinel = f'{PREFERRED_ENTITY_SENTINEL_PREFIX}{index}__'
            group_sentinels.append((sentinel, group))
            for preferred_name in sorted(set(group['names']), key=len, reverse=True):
                preferred_replacements.append((preferred_name, sentinel, group))

        for preferred_name, sentinel, _group in sorted(preferred_replacements, key=lambda item: len(item[0]), reverse=True):
            working_text = working_text.replace(preferred_name, sentinel)
    else:
        group_sentinels = []

    anonymized = normalize_fullwidth_text(working_text, restore_map)

    date_patterns = _configured_patterns(config, 'date_patterns', DEFAULT_DATE_PATTERNS)
    time_patterns = _configured_patterns(config, 'time_patterns', DEFAULT_TIME_PATTERNS)
    address_patterns = _configured_patterns(config, 'address_patterns', DEFAULT_ADDRESS_PATTERNS)
    name_patterns = _configured_patterns(config, 'name_patterns', DEFAULT_NAME_PATTERNS)
    age_patterns = _configured_patterns(config, 'age_patterns', DEFAULT_AGE_PATTERNS)

    anonymized = generalize_date_text(anonymized, restore_map, date_patterns)
    anonymized = generalize_time_text(anonymized, restore_map, time_patterns)
    anonymized = generalize_address_text(anonymized, restore_map, address_patterns)
    anonymized = anonymize_person_names(anonymized, restore_map, name_patterns)
    anonymized = generalize_age_text(anonymized, restore_map, age_patterns)
    anonymized = anonymize_contact_text(anonymized, restore_map, config)
    for sentinel, group in group_sentinels:
        if sentinel not in anonymized:
            continue
        label = str(group.get('label') or '').strip()
        original = str(group.get('original') or '').strip()
        if not label:
            continue
        anonymized = anonymized.replace(sentinel, label)
        restore_map[label] = original or str(group.get('names', [''])[0] or '')
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
