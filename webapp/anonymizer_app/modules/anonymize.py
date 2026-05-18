from dataclasses import dataclass
from typing import Any, Dict, Tuple
import re


@dataclass
class AnonymizeResult:
    text: str
    restore_map: Dict[str, Any]


def _replace_with_map(s: str, pattern: re.Pattern, repl_func) -> Tuple[str, Dict[str, str]]:
    """Helper to replace occurrences and record original->replacement map."""
    restore = {}

    def _repl(m):
        orig = m.group(0)
        new = repl_func(m)
        if orig != new:
            restore[orig] = new
        return new

    out = pattern.sub(_repl, s)
    return out, restore


def anonymize_text(text: str, template_type: str) -> AnonymizeResult:
    """Perform a lightweight regex-based anonymization.

    Rules implemented (simple heuristics):
    - 氏名＋氏 -> 患者A氏 のようにラベル化（連番）
    - 住所の詳細 -> 市内レベルへ一般化
    - 平成表記の日時（年月日と時刻） -> 月下旬午後へ一般化
    - 電話番号らしき数列 -> [電話番号]

    This is intentionally conservative and may not cover all cases.
    """
    out = text
    restore_map: Dict[str, str] = {}

    # Replace address/date/phone first to avoid name false-positives inside addresses
    # 2) 住所の詳細を市内レベルに一般化: 『...県...市...』 を『...県...市内』に
    addr_pattern = re.compile(r'([一-龯0-9０-９]+県[一-龯0-9０-９]+市)[^、。\n]*')

    def addr_repl(m):
        return m.group(1) + '内'

    out, addr_map = _replace_with_map(out, addr_pattern, addr_repl)
    restore_map.update(addr_map)

    # 3) 日時（平成NN年MM月DD日 hh:mm） -> 平成NN年MM月下旬午後
    datetime_pattern = re.compile(r'平成(\d+)年(\d+)月(\d+)日\s*\d{1,2}[:：]\d{1,2}')

    def datetime_repl(m):
        return f'平成{m.group(1)}年{m.group(2)}月下旬午後'

    out, dt_map = _replace_with_map(out, datetime_pattern, datetime_repl)
    restore_map.update(dt_map)

    # 4) 電話番号（ハイフンありor連続10-11桁） -> [電話番号]
    phone_pattern = re.compile(r'(\d{2,4}[-ー－]\d{2,4}[-ー－]\d{4}|\d{10,11})')
    out, phone_map = _replace_with_map(out, phone_pattern, lambda m: '[電話番号]')
    restore_map.update(phone_map)

    # 1) 氏名（honorific 必須）を検出して同一ラベルを割り当てる（患者ラベル）。
    #    既に『患者』や『家族』や職種ラベルが近傍にある場合は置換しない。
    name_to_label: Dict[str, str] = {}
    patient_counter = 0

    # match kanji names ending with honorific 氏/さん/様 to reduce false positives
    name_pattern = re.compile(r'([一-龯]{2,4}[一-龯]{1,3})(氏|さん|様)')

    def name_repl(m):
        nonlocal patient_counter
        orig_full = m.group(0)
        if orig_full in name_to_label:
            return name_to_label[orig_full]
        label = f'患者{chr(ord("A") + patient_counter)}' + m.group(2)
        name_to_label[orig_full] = label
        patient_counter += 1
        return label

    def _name_filter(s: str) -> str:
        tokens = ['患者', '家族', '看護師', '医師']
        def repl(m):
            span_start = m.start()
            span_end = m.end()
            context_start = max(0, span_start - 10)
            context_end = min(len(s), span_end + 10)
            ctx = s[context_start:context_end]
            for t in tokens:
                if t in ctx:
                    return m.group(0)
            return name_repl(m)
        return name_pattern.sub(repl, s)

    out = _name_filter(out)
    for k, v in name_to_label.items():
        restore_map[k] = v

    # 2) 住所の詳細を市内レベルに一般化: 『...県...市...』 を『...県...市内』に
    addr_pattern = re.compile(r'([一-龯0-9０-９]+県[一-龯0-9０-９]+市)[^、。\n]*')

    def addr_repl(m):
        return m.group(1) + '内'

    out, addr_map = _replace_with_map(out, addr_pattern, addr_repl)
    restore_map.update(addr_map)

    # 3) 日時（平成NN年MM月DD日 hh:mm） -> 平成NN年MM月下旬午後
    datetime_pattern = re.compile(r'平成(\d+)年(\d+)月(\d+)日\s*\d{1,2}[:：]\d{1,2}')

    def datetime_repl(m):
        return f'平成{m.group(1)}年{m.group(2)}月下旬午後'

    out, dt_map = _replace_with_map(out, datetime_pattern, datetime_repl)
    restore_map.update(dt_map)

    # 4) 電話番号（ハイフンありor連続10-11桁） -> [電話番号]
    phone_pattern = re.compile(r'(\d{2,4}[-ー－]\d{2,4}[-ー－]\d{4}|\d{10,11})')
    out, phone_map = _replace_with_map(out, phone_pattern, lambda m: '[電話番号]')
    restore_map.update(phone_map)

    # 5) 年齢等の数値はそのまま残すが、連続した固有識別子はラベル化の対象にする場合がある（未実装）

    return AnonymizeResult(text=out, restore_map=restore_map)


def build_prompt_payload(template_type: str, data: Dict[str, Any], source_id: str) -> Dict[str, Any]:
    return {
        'metadata': {
            'source_id': source_id,
            'template_type': template_type,
            'created_at': None,
        },
        'data': data,
    }
