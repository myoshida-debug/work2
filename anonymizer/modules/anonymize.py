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
    def replace_time(match):
        hour = int(match.group('hour'))
        anonymized = '午前' if hour < 12 else '午後'
        record_restore_segment(restore_map, anonymized, match.group(0))
        return anonymized

    text = re.sub(r'(?P<hour>\d{1,2})[:：]\d{1,2}', replace_time, text)
    text = re.sub(r'午前\d{1,2}時|午後\d{1,2}時', lambda m: record_time_restore(m, restore_map), text)
    return text


def record_time_restore(match, restore_map: dict) -> str:
    original = match.group(0)
    anonymized = '午前' if '午前' in original else '午後'
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


def anonymize_text(text: str, template_type: str = 'generic') -> AnonymizationResult:
    config = load_config(Path(__file__).resolve().parents[1] / 'config')
    restore_map = {}
    anonymized = normalize_fullwidth_text(text, restore_map)

    anonymized = generalize_date_text(anonymized, restore_map)
    anonymized = generalize_time_text(anonymized, restore_map)
    anonymized = generalize_address_text(anonymized, restore_map)
    anonymized = anonymize_person_names(anonymized, restore_map)
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


def build_prompt_payload(template_type: str, content: dict, source_id: str, title: str | None = None):
    prompt_text = create_prompt_text(template_type, content)
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


def build_result_payload(source_id: str, result_text: str, reviewer: str = 'unknown'):
    return {
        'id': f'result_{source_id}',
        'source_id': source_id,
        'result_text': result_text,
        'metadata': {
            'processed_at': None,
            'reviewer': reviewer,
        },
    }


def create_prompt_text(template_type: str, content: dict) -> str:
    lines = [f'あなたは精神科病棟の看護師です。以下の匿名化された情報をもとに、{template_type}を作成してください。', '']
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
