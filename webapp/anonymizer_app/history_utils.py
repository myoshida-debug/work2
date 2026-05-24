from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Sequence
from typing import Any


HISTORY_LIMIT = 500


OPERATION_ACTION_LABELS = {
    'network_policy_denied': 'ネットワーク拒否',
    'prompt_created': '匿名化文書作成',
    'prompt_created_manually': '手動プロンプト作成',
    'prompt_deleted': 'プロンプト削除',
    'prompt_imported_to_open': 'OpenSide取込',
    'prompt_sent_to_dmz': 'DMZ送信',
    'prompt_updated': 'プロンプト更新',
    'patient_created': '患者作成',
    'patient_deleted': '患者削除',
    'patient_imported': '患者CSV取込',
    'patient_updated': '患者更新',
    'restored_result_deleted': '復元結果削除',
    'restored_result_rerestored': '再復元',
    'result_imported_to_close': '返却JSON取込',
    'result_sent_to_dmz': '返却DMZ送信',
    'template_created': 'テンプレート作成',
    'template_deleted': 'テンプレート削除',
    'template_updated': 'テンプレート更新',
}


def operation_action_label(action: str) -> str:
    return OPERATION_ACTION_LABELS.get(action, action.replace('_', ' '))


def stringify_history_value(value: Any) -> str:
    if value is None:
        return ''

    if hasattr(value, 'strftime'):
        return value.strftime('%Y-%m-%d %H:%M:%S')

    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    if isinstance(value, (list, tuple, set)):
        return ' '.join(stringify_history_value(item) for item in value)

    return str(value)


def filter_history_items(
    items: Iterable[Any],
    query: str | None,
    value_getters: Sequence[str | Callable[[Any], Any]],
) -> list[Any]:
    normalized_query = (query or '').strip().casefold()
    history_items = list(items)
    if not normalized_query:
        return history_items

    filtered_items = []
    for item in history_items:
        search_parts = []
        for getter in value_getters:
            value = getter(item) if callable(getter) else getattr(item, getter, '')
            text = stringify_history_value(value)
            if text:
                search_parts.append(text)
        if normalized_query in ' '.join(search_parts).casefold():
            filtered_items.append(item)
    return filtered_items


def pick_selected_history_item(
    items: Sequence[Any],
    selected_value: str | None,
    key_getter: Callable[[Any], Any] | None = None,
) -> Any | None:
    if key_getter is None:
        key_getter = lambda item: getattr(item, 'pk', None)

    if selected_value not in (None, ''):
        for item in items:
            if str(key_getter(item)) == str(selected_value):
                return item

    return items[0] if items else None


def decorate_operation_logs(logs: Sequence[Any]) -> list[Any]:
    decorated_logs = []
    for log in logs:
        log.action_label = operation_action_label(getattr(log, 'action', ''))
        decorated_logs.append(log)
    return decorated_logs
