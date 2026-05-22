from __future__ import annotations

from copy import deepcopy


DEFAULT_TEMPLATE_INPUT_SCHEMA = [
    {'key': 'text', 'label': '本文', 'required': True},
]


TEMPLATE_INPUT_SCHEMAS: dict[str, list[dict[str, object]]] = {
    '入院時サマリー': [
        {'key': 'chief_complaint', 'label': '主訴', 'required': True},
        {'key': 'present_history', 'label': '現病歴', 'required': True},
        {'key': 'past_history', 'label': '既往歴', 'required': False},
        {'key': 'family_social_history', 'label': '家族歴・生活歴', 'required': False},
        {'key': 'medication_allergy', 'label': '内服薬・アレルギー', 'required': False},
        {'key': 'physical_findings', 'label': '入院時身体所見', 'required': False},
        {'key': 'test_findings', 'label': '検査所見', 'required': False},
        {'key': 'clinical_assessment', 'label': '臨床評価', 'required': False},
        {'key': 'admission_purpose', 'label': '入院目的', 'required': True},
        {'key': 'treatment_plan', 'label': '治療方針', 'required': True},
        {'key': 'notes', 'label': '留意点', 'required': False},
    ],
    '退院時サマリー': [
        {'key': 'admission_reason', 'label': '入院理由', 'required': True},
        {'key': 'hospital_course', 'label': '入院後経過', 'required': True},
        {'key': 'treatments', 'label': '実施治療', 'required': False},
        {'key': 'main_test_results', 'label': '主要検査結果', 'required': False},
        {'key': 'discharge_status', 'label': '退院時状態', 'required': True},
        {'key': 'discharge_medication', 'label': '退院処方・継続治療', 'required': False},
        {'key': 'future_plan', 'label': '今後の方針', 'required': True},
    ],
    '中間サマリー': [
        {'key': 'background', 'label': '入院目的・背景', 'required': True},
        {'key': 'course', 'label': '現在までの経過', 'required': True},
        {'key': 'current_status', 'label': '現在の状態', 'required': True},
        {'key': 'problems', 'label': '問題点', 'required': False},
        {'key': 'treatment_response', 'label': '治療・対応', 'required': False},
        {'key': 'future_plan', 'label': '今後の方針', 'required': True},
    ],
    'インシデントレポート': [
        {'key': 'datetime_place', 'label': '発生日時・場所', 'required': True},
        {'key': 'incident_level', 'label': 'インシデントレベル', 'required': False},
        {'key': 'event_detail', 'label': '発生内容', 'required': True},
        {'key': 'discovery', 'label': '発見経緯', 'required': False},
        {'key': 'patient_impact', 'label': '患者への影響', 'required': False},
        {'key': 'response', 'label': '実施対応', 'required': True},
        {'key': 'prevention', 'label': '再発防止策', 'required': False},
    ],
    '委員会議事録': [
        {
            'key': 'overview',
            'label': '開催概要',
            'required': True,
            'default': '会議名、開催日時、開催場所、参加者',
        },
        {'key': 'agenda', 'label': '議題', 'required': True},
        {'key': 'discussion', 'label': '主な議論', 'required': True},
        {'key': 'decisions', 'label': '決定事項', 'required': False},
        {'key': 'next_actions', 'label': '今後の対応', 'required': False},
    ],
    '看護計画': [
        {'key': 'patient_status', 'label': '患者の状態', 'required': True},
        {'key': 'nursing_problem', 'label': '看護問題', 'required': True},
        {'key': 'nursing_goal', 'label': '看護目標', 'required': True},
        {'key': 'observation', 'label': '観察項目', 'required': False},
        {'key': 'care', 'label': 'ケア内容', 'required': False},
        {'key': 'evaluation', 'label': '評価視点', 'required': False},
    ],
}

TEMPLATE_INPUT_SCHEMA_ALIASES: dict[str, str] = {
    '入院時サマリー（詳細版）': '入院時サマリー',
    'インシデントレポート（様式1-3）': 'インシデントレポート',
    'インシデントレポート（簡易版）': 'インシデントレポート',
}


def _canonical_template_type(template_type: str) -> str:
    return TEMPLATE_INPUT_SCHEMA_ALIASES.get(template_type, template_type)


def get_template_input_schema(template_type: str) -> list[dict[str, object]]:
    schema = TEMPLATE_INPUT_SCHEMAS.get(_canonical_template_type(template_type), DEFAULT_TEMPLATE_INPUT_SCHEMA)
    return [deepcopy(field) for field in schema]
