from __future__ import annotations

from copy import deepcopy


DEFAULT_TEMPLATE_INPUT_SCHEMA = [
    {'key': 'text', 'label': '本文', 'required': True},
]

TREATMENT_PLAN_CHECKBOX_OPTIONS = [
    {'value': '安静', 'label': '安静'},
    {'value': '輸液', 'label': '輸液'},
    {'value': '食事制限', 'label': '食事制限'},
    {'value': '薬剤調整', 'label': '薬剤調整'},
    {'value': '抗菌薬投与', 'label': '抗菌薬投与'},
    {'value': '酸素投与', 'label': '酸素投与'},
    {'value': '検査・経過観察', 'label': '検査・経過観察'},
    {'value': '処置・手術', 'label': '処置・手術'},
    {'value': 'リハビリ', 'label': 'リハビリ'},
    {'value': '退院・転院調整', 'label': '退院・転院調整'},
]


def _master_options(entries: list[tuple[str, str]]) -> list[dict[str, str]]:
    return [{'value': code, 'label': label, 'code': code} for code, label in entries]


def _textarea_field(
    label: str,
    *,
    required: bool = False,
    default: str | None = None,
    help_text: str | None = None,
    section_title: str | None = None,
) -> dict[str, object]:
    field: dict[str, object] = {
        'label': label,
        'required': required,
    }
    if default is not None:
        field['default'] = default
    if help_text:
        field['help_text'] = help_text
    if section_title:
        field['section_title'] = section_title
    return field


def _date_field(
    label: str,
    *,
    required: bool = False,
    default: str | None = None,
    help_text: str | None = None,
    section_title: str | None = None,
) -> dict[str, object]:
    field = _textarea_field(
        label,
        required=required,
        default=default,
        help_text=help_text,
        section_title=section_title,
    )
    field['input_type'] = 'date'
    return field


def _checkbox_group_field(
    label: str,
    entries: list[tuple[str, str]],
    *,
    required: bool = False,
    help_text: str = '複数選択できます。必要に応じて本文欄へ自由記載してください。',
    allow_other: bool = True,
    other_label: str = 'その他',
    other_placeholder: str = '自由入力',
    section_title: str | None = None,
) -> dict[str, object]:
    field: dict[str, object] = {
        'label': label,
        'required': required,
        'input_type': 'checkbox_group',
        'options': _master_options(entries),
        'allow_other': allow_other,
        'other_label': other_label,
        'other_placeholder': other_placeholder,
        'help_text': help_text,
    }
    if section_title:
        field['section_title'] = section_title
    return field


def _choice_group_field(
    label: str,
    entries: list[tuple[str, str]],
    *,
    required: bool = False,
    help_text: str = '該当するものを1つ選択してください。',
    section_title: str | None = None,
) -> dict[str, object]:
    return _checkbox_group_field(
        label,
        entries,
        required=required,
        help_text=help_text,
        allow_other=False,
        section_title=section_title,
    )


def _multi_choice_group_field(
    label: str,
    entries: list[tuple[str, str]],
    *,
    required: bool = False,
    help_text: str = '複数選択できます。必要に応じて本文欄へ自由記載してください。',
    section_title: str | None = None,
) -> dict[str, object]:
    return _checkbox_group_field(
        label,
        entries,
        required=required,
        help_text=help_text,
        allow_other=False,
        section_title=section_title,
    )


def _normalize_textarea_rows(value: object, default: int = 3) -> int:
    try:
        rows = int(str(value).strip())
    except Exception:
        rows = default
    return rows if rows > 0 else default


MASTER_001_ADMISSION_TYPE = [
    ('ADM001', '任意入院'),
    ('ADM002', '医療保護入院'),
    ('ADM003', '措置入院'),
    ('ADM004', '緊急措置入院'),
    ('ADM005', '応急入院'),
]

MASTER_002_PSYCHIATRIC_SYMPTOMS = [
    ('PSY001', '不眠'),
    ('PSY002', '気分の落ち込み'),
    ('PSY003', '希死念慮'),
    ('PSY004', '自殺企図後'),
    ('PSY005', '不安・焦燥'),
    ('PSY006', '幻覚'),
    ('PSY007', '妄想'),
    ('PSY008', '興奮・易刺激性'),
    ('PSY009', '多弁・躁状態'),
    ('PSY010', '意欲低下'),
    ('PSY011', '拒薬'),
    ('PSY012', '病識欠如'),
    ('PSY013', '強迫症状'),
    ('PSY014', 'パニック症状'),
    ('PSY015', '解離症状'),
    ('PSY016', '認知機能低下'),
    ('PSY017', '徘徊'),
    ('PSY018', '暴力・暴言'),
    ('PSY019', '自傷行為'),
    ('PSY020', '対人トラブル'),
    ('PSY021', '昼夜逆転'),
]

MASTER_003_LIFE_PROBLEMS = [
    ('LIF001', '食欲低下'),
    ('LIF002', '拒食'),
    ('LIF003', '過食'),
    ('LIF004', 'ADL低下'),
    ('LIF005', '清潔保持困難'),
    ('LIF006', '金銭管理困難'),
    ('LIF007', '服薬管理困難'),
    ('LIF008', '通院継続困難'),
    ('LIF009', '家族介護困難'),
    ('LIF010', '独居生活困難'),
    ('LIF011', '就労・就学困難'),
    ('LIF012', '虐待・養育問題'),
    ('LIF013', '住居問題'),
]

MASTER_004_PHYSICAL_AND_DEPENDENCY = [
    ('PHY001', 'アルコール問題'),
    ('PHY002', '薬物使用'),
    ('PHY003', '処方薬依存'),
    ('PHY004', '離脱症状'),
    ('PHY005', '身体合併症管理'),
    ('PHY006', '転倒リスク'),
    ('PHY007', '低栄養'),
    ('PHY008', '脱水'),
]

PSYCHIATRIC_SECTION_1_TITLE = '① 主訴（患者・家族が訴える主な問題）'
PSYCHIATRIC_SECTION_2_TITLE = '② 入院目的'
PSYCHIATRIC_SECTION_3_TITLE = '③ 治療方針'

MASTER_005_ADMISSION_PURPOSE_SYMPTOM_STABILIZATION = [
    ('GOAL001', '精神症状の急性増悪改善'),
    ('GOAL002', '興奮・攻撃性コントロール'),
    ('GOAL003', '自殺リスク軽減'),
    ('GOAL004', '自傷予防'),
    ('GOAL005', '拒薬改善'),
    ('GOAL006', '睡眠改善'),
    ('GOAL007', '栄養状態改善'),
    ('GOAL008', '身体状態管理'),
]

MASTER_006_ADMISSION_PURPOSE_SAFETY = [
    ('GOAL009', '本人保護'),
    ('GOAL010', '他害防止'),
    ('GOAL011', '自殺防止'),
    ('GOAL012', '行動制限下での治療'),
    ('GOAL013', '保護室管理'),
    ('GOAL014', '環境調整'),
]

MASTER_007_ADMISSION_PURPOSE_TREATMENT_INTRODUCTION = [
    ('GOAL015', '薬物療法導入'),
    ('GOAL016', '薬剤調整'),
    ('GOAL017', '副作用評価'),
    ('GOAL018', '持効性注射剤導入'),
    ('GOAL019', 'ECT検討'),
    ('GOAL020', '心理教育'),
    ('GOAL021', '疾患理解促進'),
]

MASTER_008_ADMISSION_PURPOSE_LIFE_SOCIAL_SUPPORT = [
    ('GOAL022', '生活機能回復'),
    ('GOAL023', 'ADL改善'),
    ('GOAL024', '退院支援'),
    ('GOAL025', '家族支援'),
    ('GOAL026', '介護サービス調整'),
    ('GOAL027', '施設入所調整'),
    ('GOAL028', '地域連携'),
    ('GOAL029', '社会資源導入'),
]

MASTER_009_ADMISSION_PURPOSE_DEPENDENCY = [
    ('GOAL030', '離脱管理'),
    ('GOAL031', '断酒教育'),
    ('GOAL032', '再発予防'),
]

MASTER_006_RISK_ASSESSMENT = [
    ('RISK001', '自殺リスク'),
    ('RISK002', '自傷リスク'),
    ('RISK003', '他害リスク'),
    ('RISK004', '離院リスク'),
    ('RISK005', '転倒リスク'),
    ('RISK006', '誤嚥リスク'),
    ('RISK007', '暴力リスク'),
    ('RISK008', '身体急変リスク'),
]

MASTER_010_TREATMENT_POLICY_MEDICATION = [
    ('PLAN001', '抗精神病薬調整'),
    ('PLAN002', '抗うつ薬調整'),
    ('PLAN003', '気分安定薬調整'),
    ('PLAN004', '睡眠薬調整'),
    ('PLAN005', '抗不安薬調整'),
    ('PLAN006', '副作用モニタリング'),
    ('PLAN007', '服薬アドヒアランス改善'),
    ('PLAN008', '持効性注射剤検討'),
]

MASTER_011_TREATMENT_POLICY_PSYCHOTHERAPY = [
    ('PLAN009', '支持的精神療法'),
    ('PLAN010', '心理教育'),
    ('PLAN011', '疾患教育'),
    ('PLAN012', '再発予防指導'),
    ('PLAN013', '認知行動的介入'),
    ('PLAN014', '依存症教育'),
]

MASTER_012_TREATMENT_POLICY_NURSING = [
    ('PLAN015', '行動観察強化'),
    ('PLAN016', '自殺リスク観察'),
    ('PLAN017', '転倒予防'),
    ('PLAN018', '食事・水分管理'),
    ('PLAN019', '睡眠状況観察'),
    ('PLAN020', '清潔援助'),
    ('PLAN021', '服薬確認'),
    ('PLAN022', '離院防止対応'),
]

MASTER_013_BEHAVIOR_RESTRICTIONS = [
    ('ACT001', '保護室使用'),
    ('ACT002', '隔離'),
    ('ACT003', '身体拘束'),
    ('ACT004', '行動制限最小化方針確認'),
]

MASTER_014_TREATMENT_POLICY_REHAB = [
    ('PLAN023', '作業療法導入'),
    ('PLAN024', '生活リズム調整'),
    ('PLAN025', 'デイケア連携'),
    ('PLAN026', '就労支援検討'),
    ('PLAN027', '退院前訪問検討'),
]

MASTER_015_TREATMENT_POLICY_MULTIDISCIPLINARY = [
    ('PLAN028', 'PSW介入'),
    ('PLAN029', '訪問看護調整'),
    ('PLAN030', '家族面談実施'),
    ('PLAN031', 'ケアマネ連携'),
    ('PLAN032', '行政連携'),
    ('PLAN033', '転院調整'),
    ('PLAN034', '施設調整'),
]

MASTER_009_DISCHARGE_SUPPORT = [
    ('DIS001', '病識不十分'),
    ('DIS002', '服薬継続困難'),
    ('DIS003', '家族支援不足'),
    ('DIS004', '独居'),
    ('DIS005', '住居不安定'),
    ('DIS006', '経済問題'),
    ('DIS007', 'サービス未導入'),
    ('DIS008', '就労困難'),
    ('DIS009', '継続通院困難'),
    ('DIS010', '再発リスク高い'),
]


DOCTOR_DISCHARGE_BASIC_INFO_TITLE = '基本情報'
DOCTOR_DISCHARGE_SECTION_1_TITLE = '1. 入院時主症状'
DOCTOR_DISCHARGE_SECTION_2_TITLE = '2. 入院後経過'
DOCTOR_DISCHARGE_SECTION_3_TITLE = '3. 退院時状態'
DOCTOR_DISCHARGE_SECTION_4_TITLE = '4. 退院後方針'
DOCTOR_DISCHARGE_SECTION_5_TITLE = '5. 処方'
DOCTOR_DISCHARGE_SECTION_6_TITLE = '6. 特記事項'

DOCTOR_DISCHARGE_DESTINATION_OPTIONS = [
    ('DDO001', '自宅'),
    ('DDO002', '家族宅'),
    ('DDO003', '施設'),
    ('DDO004', '転院'),
    ('DDO005', 'その他'),
]

DOCTOR_DISCHARGE_ADMISSION_TYPE_OPTIONS = [
    ('DDA001', '任意'),
    ('DDA002', '医療保護'),
    ('DDA003', '措置'),
    ('DDA004', 'その他'),
]

DOCTOR_DISCHARGE_MAIN_SYMPTOM_OPTIONS = [
    ('DDS001', '幻覚妄想'),
    ('DDS002', '希死念慮'),
    ('DDS003', '興奮'),
    ('DDS004', '不眠'),
    ('DDS005', '抑うつ'),
    ('DDS006', '躁状態'),
    ('DDS007', '拒薬'),
    ('DDS008', '病識欠如'),
    ('DDS009', '自傷'),
    ('DDS010', '他害'),
    ('DDS011', '認知機能低下'),
]

DOCTOR_DISCHARGE_TREATMENT_OPTIONS = [
    ('DDT001', '薬剤調整'),
    ('DDT002', '抗精神病薬導入'),
    ('DDT003', '抗うつ薬導入'),
    ('DDT004', '気分安定薬導入'),
    ('DDT005', '持効性注射剤導入'),
    ('DDT006', 'ECT施行'),
    ('DDT007', '精神療法'),
    ('DDT008', '心理教育'),
    ('DDT009', '作業療法'),
    ('DDT010', '行動制限実施'),
]

DOCTOR_DISCHARGE_STATUS_OPTIONS = [
    ('DDS001', '幻覚妄想改善'),
    ('DDS002', '睡眠改善'),
    ('DDS003', '希死念慮消失'),
    ('DDS004', '興奮消失'),
    ('DDS005', '感情安定'),
    ('DDS006', '病識改善'),
    ('DDS007', '服薬理解あり'),
]

DOCTOR_DISCHARGE_ADL_OPTIONS = [
    ('DAD001', '自立'),
    ('DAD002', '一部介助'),
    ('DAD003', '全介助'),
]

DOCTOR_DISCHARGE_RISK_OPTIONS = [
    ('DRK001', 'あり'),
    ('DRK002', 'なし'),
]

DOCTOR_DISCHARGE_POST_PLAN_OPTIONS = [
    ('DDP001', '外来継続'),
    ('DDP002', '訪問看護'),
    ('DDP003', 'デイケア'),
    ('DDP004', '就労支援'),
    ('DDP005', '施設利用'),
    ('DDP006', '行政支援'),
    ('DDP007', '家族支援継続'),
]

NURSING_ADMISSION_BASIC_INFO_TITLE = '基本情報'
NURSING_ADMISSION_SECTION_1_TITLE = '1. 入院時状態'
NURSING_ADMISSION_SECTION_2_TITLE = '2. 看護上の問題'
NURSING_ADMISSION_SECTION_3_TITLE = '3. 看護方針'
NURSING_ADMISSION_SECTION_4_TITLE = '4. 特記事項'

NURSING_ADMISSION_PSYCH_OPTIONS = [
    ('NAP001', '不穏'),
    ('NAP002', '興奮'),
    ('NAP003', '不安強い'),
    ('NAP004', '希死念慮'),
    ('NAP005', '自傷行為'),
    ('NAP006', '幻覚妄想'),
    ('NAP007', '拒薬'),
    ('NAP008', '多弁'),
    ('NAP009', '無為・無反応'),
    ('NAP010', '昼夜逆転'),
]

NURSING_ADMISSION_PHYSICAL_OPTIONS = [
    ('NAB001', '発熱'),
    ('NAB002', '脱水'),
    ('NAB003', '低栄養'),
    ('NAB004', '転倒リスク'),
    ('NAB005', '誤嚥リスク'),
    ('NAB006', '便秘'),
    ('NAB007', '不眠'),
]

NURSING_ADMISSION_ADL_OPTIONS = [
    ('NAA001', '自立'),
    ('NAA002', '見守り'),
    ('NAA003', '介助'),
]

NURSING_ADMISSION_PROBLEM_OPTIONS = [
    ('NAP011', '自殺リスク'),
    ('NAP012', '他害リスク'),
    ('NAP013', '離院リスク'),
    ('NAP014', '転倒リスク'),
    ('NAP015', '服薬拒否'),
    ('NAP016', '清潔保持困難'),
    ('NAP017', '睡眠障害'),
    ('NAP018', '食事摂取不良'),
]

NURSING_ADMISSION_POLICY_OPTIONS = [
    ('NPO001', '安全確保'),
    ('NPO002', '行動観察強化'),
    ('NPO003', '睡眠調整'),
    ('NPO004', '食事・水分管理'),
    ('NPO005', '清潔援助'),
    ('NPO006', '服薬支援'),
    ('NPO007', '家族支援'),
    ('NPO008', '感情表出支援'),
]

NURSING_MIDTERM_BASIC_INFO_TITLE = '基本情報'
NURSING_MIDTERM_SECTION_1_TITLE = '1. 現在の精神状態'
NURSING_MIDTERM_SECTION_2_TITLE = '2. ADL状況'
NURSING_MIDTERM_SECTION_3_TITLE = '3. 看護経過'
NURSING_MIDTERM_SECTION_4_TITLE = '4. 現在の課題'
NURSING_MIDTERM_SECTION_5_TITLE = '5. 今後の看護方針'

NURSING_MIDTERM_PSYCH_OPTIONS = [
    ('NMS001', '安定'),
    ('NMS002', '不安定'),
    ('NMS003', '不穏あり'),
    ('NMS004', '希死念慮持続'),
    ('NMS005', '幻覚妄想持続'),
    ('NMS006', '睡眠不良'),
    ('NMS007', '拒薬傾向'),
]

NURSING_MIDTERM_ADL_OPTIONS = [
    ('NMA001', '改善'),
    ('NMA002', '維持'),
    ('NMA003', '低下'),
]

NURSING_MIDTERM_COURSE_OPTIONS = [
    ('NMC001', '睡眠改善'),
    ('NMC002', '服薬受け入れ改善'),
    ('NMC003', '感情安定'),
    ('NMC004', '作業療法参加'),
    ('NMC005', '対人交流増加'),
    ('NMC006', '問題行動減少'),
]

NURSING_MIDTERM_PROBLEM_OPTIONS = [
    ('NMP001', '病識不十分'),
    ('NMP002', '服薬継続不安'),
    ('NMP003', '再発リスク'),
    ('NMP004', '家族調整必要'),
    ('NMP005', '退院先未定'),
    ('NMP006', 'サービス調整必要'),
]

NURSING_DISCHARGE_BASIC_INFO_TITLE = '基本情報'
NURSING_DISCHARGE_SECTION_1_TITLE = '1. 退院時状態'
NURSING_DISCHARGE_SECTION_2_TITLE = '2. 退院指導'
NURSING_DISCHARGE_SECTION_3_TITLE = '3. 退院後支援'
NURSING_DISCHARGE_SECTION_4_TITLE = '4. 看護評価'
NURSING_DISCHARGE_SECTION_5_TITLE = '5. 特記事項'

NURSING_DISCHARGE_PSYCH_OPTIONS = [
    ('NDS001', '安定'),
    ('NDS002', '不安残存'),
    ('NDS003', '幻覚妄想軽減'),
    ('NDS004', '希死念慮消失'),
    ('NDS005', '睡眠安定'),
    ('NDS006', '感情安定'),
]

NURSING_DISCHARGE_ADL_OPTIONS = [
    ('NDA001', '自立'),
    ('NDA002', '見守り'),
    ('NDA003', '介助'),
]

NURSING_DISCHARGE_GUIDANCE_OPTIONS = [
    ('NDG001', '服薬指導'),
    ('NDG002', '再発予防指導'),
    ('NDG003', '睡眠衛生指導'),
    ('NDG004', '家族指導'),
    ('NDG005', '外来受診説明'),
    ('NDG006', '訪問看護説明'),
    ('NDG007', '緊急時対応説明'),
]

NURSING_DISCHARGE_SUPPORT_OPTIONS = [
    ('NDS007', '外来通院'),
    ('NDS008', '訪問看護'),
    ('NDS009', 'デイケア'),
    ('NDS010', '就労支援'),
    ('NDS011', '福祉サービス'),
    ('NDS012', '家族支援'),
]

NURSING_DISCHARGE_EVAL_OPTIONS = [
    ('NDE001', '目標達成'),
    ('NDE002', '一部達成'),
    ('NDE003', '継続支援必要'),
]

OT_BASIC_INFO_TITLE = '基本情報'
OT_SECTION_1_TITLE = '1. OT導入目的'
OT_SECTION_2_TITLE = '2. 活動参加状況'
OT_SECTION_3_TITLE = '3. 作業遂行能力'
OT_SECTION_4_TITLE = '4. 対人・集団適応'
OT_SECTION_5_TITLE = '5. 精神症状・行動面の観察'
OT_SECTION_6_TITLE = '6. 生活機能評価'
OT_SECTION_7_TITLE = '7. 今後のOT方針'
OT_SECTION_8_TITLE = '8. 総合評価・自由記載'

OT_MASTER_001_PURPOSE_OPTIONS = [
    ('OTG001', '生活リズム改善'),
    ('OTG002', '活動性向上'),
    ('OTG003', '対人交流促進'),
    ('OTG004', '集中力・持続力評価'),
    ('OTG005', '作業能力評価'),
    ('OTG006', 'ストレス対処練習'),
    ('OTG007', '退院後生活準備'),
    ('OTG008', '就労・復職準備'),
    ('OTG009', '認知機能評価'),
    ('OTG010', '身体機能維持'),
]

OT_MASTER_002_ACTIVITY_PARTICIPATION_OPTIONS = [
    ('OTP001', '自発的に参加'),
    ('OTP002', '促しにより参加'),
    ('OTP003', '見学のみ'),
    ('OTP004', '途中退席あり'),
    ('OTP005', '拒否あり'),
    ('OTP006', '継続参加可能'),
    ('OTP007', '気分により変動あり'),
]

OT_BASIC_PARTICIPATION_OPTIONS = [
    ('OTF001', '個別'),
    ('OTF002', '集団'),
    ('OTF003', '見学'),
    ('OTF004', '未参加'),
]

OT_WORK_LEVEL_OPTIONS = [
    ('OTW001', '良好'),
    ('OTW002', '一部支援'),
    ('OTW003', '困難'),
]

PSW_BASIC_INFO_TITLE = '基本情報'
PSW_SECTION_1_TITLE = '1. 退院支援開始理由'
PSW_SECTION_2_TITLE = '2. 生活環境'
PSW_SECTION_3_TITLE = '3. 家族・支援者状況'
PSW_SECTION_4_TITLE = '4. 経済・制度利用'
PSW_SECTION_5_TITLE = '5. 退院後サービス調整'
PSW_SECTION_6_TITLE = '6. 退院前カンファレンス'
PSW_SECTION_7_TITLE = '7. 残課題'
PSW_SECTION_8_TITLE = '8. 総合評価・引き継ぎ事項'

PSW_DISCHARGE_DESTINATION_OPTIONS = [
    ('PSWD001', '自宅'),
    ('PSWD002', '家族宅'),
    ('PSWD003', 'グループホーム'),
    ('PSWD004', '施設'),
    ('PSWD005', '転院'),
    ('PSWD006', '未定'),
]

PSW_CONFERENCE_OPTIONS = [
    ('PSWC001', '実施済'),
    ('PSWC002', '実施予定'),
    ('PSWC003', '家族参加'),
    ('PSWC004', '訪問看護参加'),
    ('PSWC005', '相談支援参加'),
    ('PSWC006', 'ケアマネ参加'),
    ('PSWC007', '行政参加'),
    ('PSWC008', '主治医参加'),
    ('PSWC009', '看護師参加'),
    ('PSWC010', 'OT参加'),
]

HV_BASIC_INFO_TITLE = '基本情報'
HV_SECTION_1_TITLE = '1. 訪問看護導入目的'
HV_SECTION_2_TITLE = '2. 精神状態'
HV_SECTION_3_TITLE = '3. 服薬状況'
HV_SECTION_4_TITLE = '4. 生活状況'
HV_SECTION_5_TITLE = '5. 家族・支援者'
HV_SECTION_6_TITLE = '6. リスク評価'
HV_SECTION_7_TITLE = '7. 支援内容'
HV_SECTION_8_TITLE = '8. 今後の方針'
HV_SECTION_9_TITLE = '9. 総合評価・申し送り'

HV_VISIT_FREQUENCY_OPTIONS = [
    ('HVF001', '週1回'),
    ('HVF002', '週2回'),
    ('HVF003', '週3回以上'),
    ('HVF004', '随時'),
]

HV_LIFE_LEVEL_OPTIONS = [
    ('HVL001', '安定'),
    ('HVL002', '一部支援'),
    ('HVL003', '要支援'),
]

HV_RISK_STATUS_OPTIONS = [
    ('HVR001', 'あり'),
    ('HVR002', 'なし'),
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
        {
            'key': 'treatment_plan',
            'label': '治療方針',
            'required': True,
            'input_type': 'checkbox_group',
            'options': TREATMENT_PLAN_CHECKBOX_OPTIONS,
            'allow_other': True,
            'other_label': 'その他',
            'other_placeholder': '自由入力',
            'help_text': '複数選択できます。その他を選ぶ場合は内容を入力してください。',
        },
        {'key': 'notes', 'label': '留意点', 'required': False},
    ],
    '精神科入院時サマリー': [
        {'key': 'basic_info', **_textarea_field('基本情報', section_title='基本情報')},
        {'key': 'admission_type', **_checkbox_group_field('入院形態', MASTER_001_ADMISSION_TYPE, required=True, section_title='入院形態')},
        {'key': 'psych_symptoms', **_checkbox_group_field('精神症状', MASTER_002_PSYCHIATRIC_SYMPTOMS, section_title=PSYCHIATRIC_SECTION_1_TITLE)},
        {'key': 'life_issues', **_checkbox_group_field('行動・生活面', MASTER_003_LIFE_PROBLEMS, section_title=PSYCHIATRIC_SECTION_1_TITLE)},
        {'key': 'physical_dependency', **_checkbox_group_field('依存・身体関連', MASTER_004_PHYSICAL_AND_DEPENDENCY, section_title=PSYCHIATRIC_SECTION_1_TITLE)},
        {'key': 'free_comment', **_textarea_field('自由記載', section_title=PSYCHIATRIC_SECTION_1_TITLE)},
        {'key': 'admission_purpose_symptom_stabilization', **_checkbox_group_field('症状安定化', MASTER_005_ADMISSION_PURPOSE_SYMPTOM_STABILIZATION, section_title=PSYCHIATRIC_SECTION_2_TITLE)},
        {'key': 'admission_purpose_safety', **_checkbox_group_field('安全確保', MASTER_006_ADMISSION_PURPOSE_SAFETY, section_title=PSYCHIATRIC_SECTION_2_TITLE)},
        {'key': 'admission_purpose_treatment_introduction', **_checkbox_group_field('治療導入・調整', MASTER_007_ADMISSION_PURPOSE_TREATMENT_INTRODUCTION, section_title=PSYCHIATRIC_SECTION_2_TITLE)},
        {'key': 'admission_purpose_life_social_support', **_checkbox_group_field('生活・社会支援', MASTER_008_ADMISSION_PURPOSE_LIFE_SOCIAL_SUPPORT, section_title=PSYCHIATRIC_SECTION_2_TITLE)},
        {'key': 'admission_purpose_dependency', **_checkbox_group_field('依存症関連', MASTER_009_ADMISSION_PURPOSE_DEPENDENCY, section_title=PSYCHIATRIC_SECTION_2_TITLE)},
        {'key': 'admission_purpose_other', **_textarea_field('自由記載', section_title=PSYCHIATRIC_SECTION_2_TITLE)},
        {'key': 'treatment_policy_medication', **_checkbox_group_field('薬物療法', MASTER_010_TREATMENT_POLICY_MEDICATION, section_title=PSYCHIATRIC_SECTION_3_TITLE)},
        {'key': 'treatment_policy_psychotherapy', **_checkbox_group_field('精神療法・心理支援', MASTER_011_TREATMENT_POLICY_PSYCHOTHERAPY, section_title=PSYCHIATRIC_SECTION_3_TITLE)},
        {'key': 'treatment_policy_nursing', **_checkbox_group_field('看護・行動観察', MASTER_012_TREATMENT_POLICY_NURSING, section_title=PSYCHIATRIC_SECTION_3_TITLE)},
        {'key': 'behavior_restrictions', **_checkbox_group_field('行動制限', MASTER_013_BEHAVIOR_RESTRICTIONS, section_title=PSYCHIATRIC_SECTION_3_TITLE)},
        {'key': 'treatment_policy_rehab', **_checkbox_group_field('リハビリ・社会復帰', MASTER_014_TREATMENT_POLICY_REHAB, section_title=PSYCHIATRIC_SECTION_3_TITLE)},
        {'key': 'treatment_policy_multidisciplinary', **_checkbox_group_field('多職種・地域連携', MASTER_015_TREATMENT_POLICY_MULTIDISCIPLINARY, section_title=PSYCHIATRIC_SECTION_3_TITLE)},
        {'key': 'treatment_policy_other', **_textarea_field('自由記載', section_title=PSYCHIATRIC_SECTION_3_TITLE)},
        {'key': 'risk_assessment', **_checkbox_group_field('リスク評価', MASTER_006_RISK_ASSESSMENT, required=True, section_title='リスク評価')},
        {'key': 'discharge_support_tasks', **_checkbox_group_field('退院支援課題', MASTER_009_DISCHARGE_SUPPORT, required=True, section_title='退院支援課題')},
        {'key': 'multidisciplinary_sharing', **_textarea_field('多職種共有', section_title='多職種共有')},
        {'key': 'discharge_goal', **_textarea_field('退院目標', required=True, section_title='退院目標')},
    ],
    '精神科退院時サマリー（医師用）': [
        {'key': 'discharge_date', **_date_field('退院日', required=True, section_title=DOCTOR_DISCHARGE_BASIC_INFO_TITLE)},
        {'key': 'hospitalization_period', **_textarea_field('入院期間', required=True, section_title=DOCTOR_DISCHARGE_BASIC_INFO_TITLE)},
        {'key': 'ward', **_textarea_field('病棟', required=True, section_title=DOCTOR_DISCHARGE_BASIC_INFO_TITLE)},
        {'key': 'attending_physician', **_textarea_field('主治医', required=True, section_title=DOCTOR_DISCHARGE_BASIC_INFO_TITLE)},
        {'key': 'discharge_destination', **_choice_group_field('退院先', DOCTOR_DISCHARGE_DESTINATION_OPTIONS, required=True, section_title=DOCTOR_DISCHARGE_BASIC_INFO_TITLE)},
        {'key': 'admission_type', **_choice_group_field('入院形態', DOCTOR_DISCHARGE_ADMISSION_TYPE_OPTIONS, required=True, section_title=DOCTOR_DISCHARGE_BASIC_INFO_TITLE)},
        {'key': 'main_symptoms', **_multi_choice_group_field('精神症状', DOCTOR_DISCHARGE_MAIN_SYMPTOM_OPTIONS, required=True, section_title=DOCTOR_DISCHARGE_SECTION_1_TITLE)},
        {'key': 'treatment_content', **_multi_choice_group_field('治療内容', DOCTOR_DISCHARGE_TREATMENT_OPTIONS, required=True, section_title=DOCTOR_DISCHARGE_SECTION_2_TITLE)},
        {'key': 'course', **_textarea_field('経過', required=True, section_title=DOCTOR_DISCHARGE_SECTION_2_TITLE)},
        {'key': 'mental_state', **_multi_choice_group_field('精神状態', DOCTOR_DISCHARGE_STATUS_OPTIONS, required=True, section_title=DOCTOR_DISCHARGE_SECTION_3_TITLE)},
        {'key': 'adl', **_choice_group_field('ADL', DOCTOR_DISCHARGE_ADL_OPTIONS, required=True, section_title=DOCTOR_DISCHARGE_SECTION_3_TITLE)},
        {'key': 'risk_suicide', **_choice_group_field('自殺リスク', DOCTOR_DISCHARGE_RISK_OPTIONS, required=True, section_title=DOCTOR_DISCHARGE_SECTION_3_TITLE)},
        {'key': 'risk_harm', **_choice_group_field('他害リスク', DOCTOR_DISCHARGE_RISK_OPTIONS, required=True, section_title=DOCTOR_DISCHARGE_SECTION_3_TITLE)},
        {'key': 'risk_leave_hospital', **_choice_group_field('離院リスク', DOCTOR_DISCHARGE_RISK_OPTIONS, required=True, section_title=DOCTOR_DISCHARGE_SECTION_3_TITLE)},
        {'key': 'risk_relapse', **_choice_group_field('再発リスク', DOCTOR_DISCHARGE_RISK_OPTIONS, required=True, section_title=DOCTOR_DISCHARGE_SECTION_3_TITLE)},
        {'key': 'post_discharge_policy', **_multi_choice_group_field('退院後方針', DOCTOR_DISCHARGE_POST_PLAN_OPTIONS, required=True, section_title=DOCTOR_DISCHARGE_SECTION_4_TITLE)},
        {'key': 'discharge_prescription', **_textarea_field('処方', section_title=DOCTOR_DISCHARGE_SECTION_5_TITLE)},
        {'key': 'special_notes', **_textarea_field('特記事項', section_title=DOCTOR_DISCHARGE_SECTION_6_TITLE)},
    ],
    '看護入院時サマリー': [
        {'key': 'admission_date', **_date_field('入院日', required=True, section_title=NURSING_ADMISSION_BASIC_INFO_TITLE)},
        {'key': 'ward', **_textarea_field('病棟', required=True, section_title=NURSING_ADMISSION_BASIC_INFO_TITLE)},
        {'key': 'primary_nurse', **_textarea_field('担当看護師', required=True, section_title=NURSING_ADMISSION_BASIC_INFO_TITLE)},
        {'key': 'key_person', **_textarea_field('キーパーソン', section_title=NURSING_ADMISSION_BASIC_INFO_TITLE)},
        {'key': 'mental_state', **_multi_choice_group_field('精神状態', NURSING_ADMISSION_PSYCH_OPTIONS, required=True, section_title=NURSING_ADMISSION_SECTION_1_TITLE)},
        {'key': 'physical_state', **_multi_choice_group_field('身体状態', NURSING_ADMISSION_PHYSICAL_OPTIONS, required=True, section_title=NURSING_ADMISSION_SECTION_1_TITLE)},
        {'key': 'adl_meal', **_choice_group_field('食事', NURSING_ADMISSION_ADL_OPTIONS, required=True, section_title=NURSING_ADMISSION_SECTION_1_TITLE)},
        {'key': 'adl_excretion', **_choice_group_field('排泄', NURSING_ADMISSION_ADL_OPTIONS, required=True, section_title=NURSING_ADMISSION_SECTION_1_TITLE)},
        {'key': 'adl_bathing', **_choice_group_field('入浴', NURSING_ADMISSION_ADL_OPTIONS, required=True, section_title=NURSING_ADMISSION_SECTION_1_TITLE)},
        {'key': 'adl_dressing', **_choice_group_field('更衣', NURSING_ADMISSION_ADL_OPTIONS, required=True, section_title=NURSING_ADMISSION_SECTION_1_TITLE)},
        {'key': 'adl_mobility', **_choice_group_field('移動', NURSING_ADMISSION_ADL_OPTIONS, required=True, section_title=NURSING_ADMISSION_SECTION_1_TITLE)},
        {'key': 'nursing_problems', **_multi_choice_group_field('看護上の問題', NURSING_ADMISSION_PROBLEM_OPTIONS, required=True, section_title=NURSING_ADMISSION_SECTION_2_TITLE)},
        {'key': 'nursing_policy', **_multi_choice_group_field('看護方針', NURSING_ADMISSION_POLICY_OPTIONS, required=True, section_title=NURSING_ADMISSION_SECTION_3_TITLE)},
        {'key': 'special_notes', **_textarea_field('特記事項', section_title=NURSING_ADMISSION_SECTION_4_TITLE)},
    ],
    '看護中間サマリー': [
        {'key': 'created_date', **_date_field('作成日', required=True, section_title=NURSING_MIDTERM_BASIC_INFO_TITLE)},
        {'key': 'hospitalization_period', **_textarea_field('入院期間', required=True, section_title=NURSING_MIDTERM_BASIC_INFO_TITLE)},
        {'key': 'primary_nurse', **_textarea_field('担当看護師', required=True, section_title=NURSING_MIDTERM_BASIC_INFO_TITLE)},
        {'key': 'current_mental_state', **_multi_choice_group_field('現在の精神状態', NURSING_MIDTERM_PSYCH_OPTIONS, required=True, section_title=NURSING_MIDTERM_SECTION_1_TITLE)},
        {'key': 'adl_meal', **_choice_group_field('食事', NURSING_MIDTERM_ADL_OPTIONS, required=True, section_title=NURSING_MIDTERM_SECTION_2_TITLE)},
        {'key': 'adl_excretion', **_choice_group_field('排泄', NURSING_MIDTERM_ADL_OPTIONS, required=True, section_title=NURSING_MIDTERM_SECTION_2_TITLE)},
        {'key': 'adl_cleanliness', **_choice_group_field('清潔', NURSING_MIDTERM_ADL_OPTIONS, required=True, section_title=NURSING_MIDTERM_SECTION_2_TITLE)},
        {'key': 'adl_activity', **_choice_group_field('活動性', NURSING_MIDTERM_ADL_OPTIONS, required=True, section_title=NURSING_MIDTERM_SECTION_2_TITLE)},
        {'key': 'nursing_course', **_multi_choice_group_field('看護経過', NURSING_MIDTERM_COURSE_OPTIONS, required=True, section_title=NURSING_MIDTERM_SECTION_3_TITLE)},
        {'key': 'current_problems', **_multi_choice_group_field('現在の課題', NURSING_MIDTERM_PROBLEM_OPTIONS, required=True, section_title=NURSING_MIDTERM_SECTION_4_TITLE)},
        {'key': 'future_nursing_policy', **_textarea_field('今後の看護方針', required=True, section_title=NURSING_MIDTERM_SECTION_5_TITLE)},
    ],
    '看護退院時サマリー': [
        {'key': 'discharge_date', **_date_field('退院日', required=True, section_title=NURSING_DISCHARGE_BASIC_INFO_TITLE)},
        {'key': 'discharge_destination', **_textarea_field('退院先', required=True, section_title=NURSING_DISCHARGE_BASIC_INFO_TITLE)},
        {'key': 'primary_nurse', **_textarea_field('担当看護師', required=True, section_title=NURSING_DISCHARGE_BASIC_INFO_TITLE)},
        {'key': 'mental_state', **_multi_choice_group_field('精神状態', NURSING_DISCHARGE_PSYCH_OPTIONS, required=True, section_title=NURSING_DISCHARGE_SECTION_1_TITLE)},
        {'key': 'adl_meal', **_choice_group_field('食事', NURSING_DISCHARGE_ADL_OPTIONS, required=True, section_title=NURSING_DISCHARGE_SECTION_1_TITLE)},
        {'key': 'adl_excretion', **_choice_group_field('排泄', NURSING_DISCHARGE_ADL_OPTIONS, required=True, section_title=NURSING_DISCHARGE_SECTION_1_TITLE)},
        {'key': 'adl_bathing', **_choice_group_field('入浴', NURSING_DISCHARGE_ADL_OPTIONS, required=True, section_title=NURSING_DISCHARGE_SECTION_1_TITLE)},
        {'key': 'adl_medication', **_choice_group_field('服薬管理', NURSING_DISCHARGE_ADL_OPTIONS, required=True, section_title=NURSING_DISCHARGE_SECTION_1_TITLE)},
        {'key': 'discharge_instruction', **_multi_choice_group_field('退院指導', NURSING_DISCHARGE_GUIDANCE_OPTIONS, required=True, section_title=NURSING_DISCHARGE_SECTION_2_TITLE)},
        {'key': 'post_discharge_support', **_multi_choice_group_field('退院後支援', NURSING_DISCHARGE_SUPPORT_OPTIONS, required=True, section_title=NURSING_DISCHARGE_SECTION_3_TITLE)},
        {'key': 'nursing_evaluation', **_choice_group_field('看護評価', NURSING_DISCHARGE_EVAL_OPTIONS, required=True, section_title=NURSING_DISCHARGE_SECTION_4_TITLE)},
        {'key': 'special_notes', **_textarea_field('特記事項', section_title=NURSING_DISCHARGE_SECTION_5_TITLE)},
    ],
    'OT評価サマリー': [
        {'key': 'evaluation_date', **_date_field('評価日', required=True, section_title=OT_BASIC_INFO_TITLE)},
        {'key': 'evaluator', **_textarea_field('評価者', required=True, section_title=OT_BASIC_INFO_TITLE)},
        {'key': 'ward', **_textarea_field('病棟', required=True, section_title=OT_BASIC_INFO_TITLE)},
        {'key': 'attending_physician', **_textarea_field('主治医', required=True, section_title=OT_BASIC_INFO_TITLE)},
        {'key': 'participation_form', **_choice_group_field('参加形態', OT_BASIC_PARTICIPATION_OPTIONS, required=True, section_title=OT_BASIC_INFO_TITLE)},
        {'key': 'ot_purpose', **_multi_choice_group_field('OT導入目的', OT_MASTER_001_PURPOSE_OPTIONS, required=True, section_title=OT_SECTION_1_TITLE)},
        {'key': 'activity_participation', **_multi_choice_group_field('活動参加状況', OT_MASTER_002_ACTIVITY_PARTICIPATION_OPTIONS, required=True, section_title=OT_SECTION_2_TITLE)},
        {'key': 'work_understanding', **_choice_group_field('理解力', OT_WORK_LEVEL_OPTIONS, required=True, section_title=OT_SECTION_3_TITLE)},
        {'key': 'work_concentration', **_choice_group_field('集中力', OT_WORK_LEVEL_OPTIONS, required=True, section_title=OT_SECTION_3_TITLE)},
        {'key': 'work_persistence', **_choice_group_field('持続力', OT_WORK_LEVEL_OPTIONS, required=True, section_title=OT_SECTION_3_TITLE)},
        {'key': 'work_sequence', **_choice_group_field('段取り', OT_WORK_LEVEL_OPTIONS, required=True, section_title=OT_SECTION_3_TITLE)},
        {'key': 'work_dexterity', **_choice_group_field('巧緻性', OT_WORK_LEVEL_OPTIONS, required=True, section_title=OT_SECTION_3_TITLE)},
        {'key': 'work_safety', **_choice_group_field('安全配慮', OT_WORK_LEVEL_OPTIONS, required=True, section_title=OT_SECTION_3_TITLE)},
        {'key': 'work_completion', **_choice_group_field('完成度', OT_WORK_LEVEL_OPTIONS, required=True, section_title=OT_SECTION_3_TITLE)},
        {'key': 'interpersonal_adaptation', **_multi_choice_group_field('対人・集団適応', [
            ('OTS001', '他者交流良好'),
            ('OTS002', '職員とは交流可'),
            ('OTS003', '他患者との交流少ない'),
            ('OTS004', '過干渉あり'),
            ('OTS005', '被刺激性あり'),
            ('OTS006', '対人緊張あり'),
            ('OTS007', '集団参加困難'),
            ('OTS008', 'ルール理解可能'),
            ('OTS009', 'トラブルなし'),
            ('OTS010', 'トラブルあり'),
        ], section_title=OT_SECTION_4_TITLE)},
        {'key': 'psych_observation', **_multi_choice_group_field('精神症状・行動面の観察', [
            ('OTM001', '不安あり'),
            ('OTM002', '抑うつあり'),
            ('OTM003', '意欲低下'),
            ('OTM004', '易刺激性'),
            ('OTM005', '幻覚妄想の影響あり'),
            ('OTM006', '疲労感あり'),
            ('OTM007', '焦燥あり'),
            ('OTM008', '拒否的'),
            ('OTM009', '落ち着きあり'),
            ('OTM010', '表情改善'),
        ], section_title=OT_SECTION_5_TITLE)},
        {'key': 'life_function', **_multi_choice_group_field('生活機能評価', [
            ('OTL001', '生活リズム不安定'),
            ('OTL002', '日中活動量不足'),
            ('OTL003', '趣味活動なし'),
            ('OTL004', '役割喪失感あり'),
            ('OTL005', '家事能力低下'),
            ('OTL006', '金銭管理不安'),
            ('OTL007', '外出不安'),
            ('OTL008', '服薬自己管理不安'),
            ('OTL009', '退院後活動先が必要'),
        ], section_title=OT_SECTION_6_TITLE)},
        {'key': 'ot_policy', **_multi_choice_group_field('今後のOT方針', [
            ('OTPOL001', '個別OT継続'),
            ('OTPOL002', '集団OT継続'),
            ('OTPOL003', '活動量増加を目指す'),
            ('OTPOL004', '生活リズム調整'),
            ('OTPOL005', '対人交流練習'),
            ('OTPOL006', '作業耐久性向上'),
            ('OTPOL007', 'ストレス対処法獲得'),
            ('OTPOL008', '退院後活動先検討'),
            ('OTPOL009', 'デイケア移行検討'),
            ('OTPOL010', '就労支援連携'),
        ], required=True, section_title=OT_SECTION_7_TITLE)},
        {'key': 'overall_evaluation', **_textarea_field('総合評価・自由記載', section_title=OT_SECTION_8_TITLE)},
    ],
    'PSW退院支援サマリー': [
        {'key': 'created_date', **_date_field('作成日', required=True, section_title=PSW_BASIC_INFO_TITLE)},
        {'key': 'psw', **_textarea_field('担当PSW', required=True, section_title=PSW_BASIC_INFO_TITLE)},
        {'key': 'planned_discharge_date', **_date_field('退院予定日', required=True, section_title=PSW_BASIC_INFO_TITLE)},
        {'key': 'discharge_destination', **_choice_group_field('退院先', PSW_DISCHARGE_DESTINATION_OPTIONS, required=True, section_title=PSW_BASIC_INFO_TITLE)},
        {'key': 'key_person', **_textarea_field('キーパーソン', required=True, section_title=PSW_BASIC_INFO_TITLE)},
        {'key': 'support_agencies', **_textarea_field('主な支援機関', required=True, section_title=PSW_BASIC_INFO_TITLE)},
        {'key': 'support_start_reason', **_multi_choice_group_field('退院支援開始理由', [
            ('PSW001', '独居'),
            ('PSW002', '家族支援不足'),
            ('PSW003', '住居問題'),
            ('PSW004', '経済問題'),
            ('PSW005', '服薬管理困難'),
            ('PSW006', '通院継続困難'),
            ('PSW007', '病識不十分'),
            ('PSW008', '再発リスク高い'),
            ('PSW009', '介護サービス調整必要'),
            ('PSW010', '障害福祉サービス調整必要'),
            ('PSW011', '施設入所調整必要'),
            ('PSW012', '虐待・養育問題あり'),
        ], required=True, section_title=PSW_SECTION_1_TITLE)},
        {'key': 'living_environment', **_multi_choice_group_field('生活環境', [
            ('ENV001', '自宅退院可能'),
            ('ENV002', '家族同居可能'),
            ('ENV003', '独居継続予定'),
            ('ENV004', '住居なし'),
            ('ENV005', '住居環境調整必要'),
            ('ENV006', '近隣トラブルあり'),
            ('ENV007', '金銭管理困難'),
            ('ENV008', '買い物困難'),
            ('ENV009', '食事確保困難'),
            ('ENV010', '清潔保持困難'),
        ], section_title=PSW_SECTION_2_TITLE)},
        {'key': 'family_support_status', **_multi_choice_group_field('家族・支援者状況', [
            ('FAM001', '家族協力あり'),
            ('FAM002', '家族協力限定的'),
            ('FAM003', '家族受け入れ困難'),
            ('FAM004', '家族疲弊あり'),
            ('FAM005', 'キーパーソン不在'),
            ('FAM006', '後見人あり'),
            ('FAM007', '相談支援専門員あり'),
            ('FAM008', 'ケアマネあり'),
            ('FAM009', '行政担当あり'),
        ], section_title=PSW_SECTION_3_TITLE)},
        {'key': 'economic_systems', **_multi_choice_group_field('経済・制度利用', [
            ('SOC001', '障害年金'),
            ('SOC002', '生活保護'),
            ('SOC003', '自立支援医療'),
            ('SOC004', '精神障害者保健福祉手帳'),
            ('SOC005', '傷病手当金'),
            ('SOC006', '介護保険'),
            ('SOC007', '障害福祉サービス'),
            ('SOC008', '成年後見制度'),
            ('SOC009', '医療費相談必要'),
            ('SOC010', '未申請・申請支援必要'),
        ], section_title=PSW_SECTION_4_TITLE)},
        {'key': 'service_coordination', **_multi_choice_group_field('退院後サービス調整', [
            ('SUP001', '外来予約済'),
            ('SUP002', '訪問看護調整済'),
            ('SUP003', 'デイケア調整済'),
            ('SUP004', '相談支援事業所連携済'),
            ('SUP005', '居宅介護支援事業所連携済'),
            ('SUP006', 'ヘルパー導入'),
            ('SUP007', 'グループホーム調整'),
            ('SUP008', '施設入所調整'),
            ('SUP009', '行政連携'),
            ('SUP010', '地域包括支援センター連携'),
        ], section_title=PSW_SECTION_5_TITLE)},
        {'key': 'discharge_conference', **_multi_choice_group_field('退院前カンファレンス', PSW_CONFERENCE_OPTIONS, section_title=PSW_SECTION_6_TITLE)},
        {'key': 'remaining_tasks', **_multi_choice_group_field('残課題', [
            ('ISS001', '退院先未確定'),
            ('ISS002', '家族調整継続'),
            ('ISS003', '金銭管理支援必要'),
            ('ISS004', '服薬管理支援必要'),
            ('ISS005', '通院継続不安'),
            ('ISS006', '再入院リスクあり'),
            ('ISS007', 'サービス利用拒否あり'),
            ('ISS008', '本人同意不十分'),
            ('ISS009', '緊急時対応未整理'),
        ], required=True, section_title=PSW_SECTION_7_TITLE)},
        {'key': 'handover_notes', **_textarea_field('総合評価・引き継ぎ事項', section_title=PSW_SECTION_8_TITLE)},
    ],
    '精神科訪問看護サマリー': [
        {'key': 'created_date', **_date_field('作成日', required=True, section_title=HV_BASIC_INFO_TITLE)},
        {'key': 'user_name', **_textarea_field('利用者氏名', required=True, section_title=HV_BASIC_INFO_TITLE)},
        {'key': 'attending_physician', **_textarea_field('主治医', required=True, section_title=HV_BASIC_INFO_TITLE)},
        {'key': 'visiting_nursing_agency', **_textarea_field('訪問看護事業所', required=True, section_title=HV_BASIC_INFO_TITLE)},
        {'key': 'visit_frequency', **_choice_group_field('訪問頻度', HV_VISIT_FREQUENCY_OPTIONS, required=True, section_title=HV_BASIC_INFO_TITLE)},
        {'key': 'visit_purpose', **_textarea_field('訪問目的', required=True, section_title=HV_BASIC_INFO_TITLE)},
        {'key': 'introduction_purpose', **_multi_choice_group_field('訪問看護導入目的', [
            ('HVG001', '服薬管理'),
            ('HVG002', '症状観察'),
            ('HVG003', '再発予防'),
            ('HVG004', '生活リズム調整'),
            ('HVG005', '睡眠状況確認'),
            ('HVG006', '食事・水分確認'),
            ('HVG007', '清潔保持支援'),
            ('HVG008', '金銭管理支援'),
            ('HVG009', '対人関係支援'),
            ('HVG010', '家族支援'),
            ('HVG011', '受診継続支援'),
            ('HVG012', '危機介入'),
        ], required=True, section_title=HV_SECTION_1_TITLE)},
        {'key': 'mental_state', **_multi_choice_group_field('精神状態', [
            ('HVM001', '安定'),
            ('HVM002', '不安あり'),
            ('HVM003', '抑うつあり'),
            ('HVM004', '焦燥あり'),
            ('HVM005', '不眠あり'),
            ('HVM006', '幻覚あり'),
            ('HVM007', '妄想あり'),
            ('HVM008', '易刺激性あり'),
            ('HVM009', '希死念慮あり'),
            ('HVM010', '自傷リスクあり'),
            ('HVM011', '他害リスクあり'),
            ('HVM012', '病識不十分'),
        ], required=True, section_title=HV_SECTION_2_TITLE)},
        {'key': 'medication_status', **_multi_choice_group_field('服薬状況', [
            ('MED001', '自己管理可能'),
            ('MED002', '一部支援必要'),
            ('MED003', '家族管理'),
            ('MED004', '訪問看護で確認'),
            ('MED005', '飲み忘れあり'),
            ('MED006', '拒薬あり'),
            ('MED007', '過量服薬リスクあり'),
            ('MED008', '副作用あり'),
            ('MED009', 'LAI使用中'),
        ], required=True, section_title=HV_SECTION_3_TITLE)},
        {'key': 'living_food', **_choice_group_field('食事', HV_LIFE_LEVEL_OPTIONS, required=True, section_title=HV_SECTION_4_TITLE)},
        {'key': 'living_sleep', **_choice_group_field('睡眠', HV_LIFE_LEVEL_OPTIONS, required=True, section_title=HV_SECTION_4_TITLE)},
        {'key': 'living_cleanliness', **_choice_group_field('清潔', HV_LIFE_LEVEL_OPTIONS, required=True, section_title=HV_SECTION_4_TITLE)},
        {'key': 'living_housework', **_choice_group_field('掃除・洗濯', HV_LIFE_LEVEL_OPTIONS, required=True, section_title=HV_SECTION_4_TITLE)},
        {'key': 'living_finance', **_choice_group_field('金銭管理', HV_LIFE_LEVEL_OPTIONS, required=True, section_title=HV_SECTION_4_TITLE)},
        {'key': 'living_visit', **_choice_group_field('通院', HV_LIFE_LEVEL_OPTIONS, required=True, section_title=HV_SECTION_4_TITLE)},
        {'key': 'living_relationships', **_choice_group_field('対人関係', HV_LIFE_LEVEL_OPTIONS, required=True, section_title=HV_SECTION_4_TITLE)},
        {'key': 'family_support', **_multi_choice_group_field('家族・支援者', [
            ('FHV001', '家族支援あり'),
            ('FHV002', '家族負担あり'),
            ('FHV003', '家族関係不安定'),
            ('FHV004', '独居'),
            ('FHV005', 'キーパーソンあり'),
            ('FHV006', '支援者不在'),
            ('FHV007', '相談支援専門員あり'),
            ('FHV008', 'ケアマネあり'),
            ('FHV009', '行政関与あり'),
        ], section_title=HV_SECTION_5_TITLE)},
        {'key': 'risk_suicide', **_choice_group_field('自殺リスク', HV_RISK_STATUS_OPTIONS, required=True, section_title=HV_SECTION_6_TITLE)},
        {'key': 'risk_self_harm', **_choice_group_field('自傷リスク', HV_RISK_STATUS_OPTIONS, required=True, section_title=HV_SECTION_6_TITLE)},
        {'key': 'risk_harm', **_choice_group_field('他害リスク', HV_RISK_STATUS_OPTIONS, required=True, section_title=HV_SECTION_6_TITLE)},
        {'key': 'risk_medication_stop', **_choice_group_field('服薬中断リスク', HV_RISK_STATUS_OPTIONS, required=True, section_title=HV_SECTION_6_TITLE)},
        {'key': 'risk_relapse', **_choice_group_field('再発リスク', HV_RISK_STATUS_OPTIONS, required=True, section_title=HV_SECTION_6_TITLE)},
        {'key': 'risk_life_breakdown', **_choice_group_field('生活破綻リスク', HV_RISK_STATUS_OPTIONS, required=True, section_title=HV_SECTION_6_TITLE)},
        {'key': 'risk_abuse_neglect', **_choice_group_field('虐待・ネグレクト', HV_RISK_STATUS_OPTIONS, required=True, section_title=HV_SECTION_6_TITLE)},
        {'key': 'risk_notes', **_textarea_field('備考', section_title=HV_SECTION_6_TITLE)},
        {'key': 'support_content', **_multi_choice_group_field('支援内容', [
            ('SUPH001', '服薬確認'),
            ('SUPH002', '症状観察'),
            ('SUPH003', '傾聴'),
            ('SUPH004', '生活指導'),
            ('SUPH005', '睡眠衛生指導'),
            ('SUPH006', '受診勧奨'),
            ('SUPH007', '家族相談'),
            ('SUPH008', '危機時対応'),
            ('SUPH009', '社会資源調整'),
            ('SUPH010', '関係機関連絡'),
        ], required=True, section_title=HV_SECTION_7_TITLE)},
        {'key': 'future_policy', **_multi_choice_group_field('今後の方針', [
            ('POL001', '訪問継続'),
            ('POL002', '訪問頻度増加'),
            ('POL003', '訪問頻度減少'),
            ('POL004', '主治医へ報告'),
            ('POL005', '家族面談調整'),
            ('POL006', 'カンファレンス実施'),
            ('POL007', 'サービス追加検討'),
            ('POL008', '緊急時対応確認'),
            ('POL009', '再入院検討'),
        ], required=True, section_title=HV_SECTION_8_TITLE)},
        {'key': 'overall_evaluation', **_textarea_field('総合評価・申し送り', section_title=HV_SECTION_9_TITLE)},
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
            'default': '会議名：\n開催日時：\n開催場所：\n参加者：',
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
    '精神科退院時サマリー': '精神科退院時サマリー（医師用）',
    'インシデントレポート（様式1-3）': 'インシデントレポート',
    'インシデントレポート（簡易版）': 'インシデントレポート',
}


def _canonical_template_type(template_type: str) -> str:
    return TEMPLATE_INPUT_SCHEMA_ALIASES.get(template_type, template_type)


def _load_template_input_default_overrides() -> dict[str, dict[str, object]]:
    try:
        from .models import TemplateInputDefault
    except Exception:
        return {}

    overrides: dict[str, dict[str, object]] = {}
    try:
        for row in TemplateInputDefault.objects.all().only('template_type', 'field_key', 'default_text', 'required_override'):
            overrides.setdefault(row.template_type, {})[row.field_key] = {
                'default_text': row.default_text,
                'required_override': row.required_override,
            }
    except Exception:
        return {}
    return overrides


def _load_template_input_checkbox_option_overrides() -> dict[str, dict[str, dict[str, object]]]:
    try:
        from .models import TemplateInputCheckboxGroup
    except Exception:
        return {}

    overrides: dict[str, dict[str, dict[str, object]]] = {}
    try:
        groups = TemplateInputCheckboxGroup.objects.prefetch_related('options').all().only('template_type', 'field_key')
        for group in groups:
            options = []
            for option in group.options.all():
                text = str(getattr(option, 'text', '') or '').strip()
                if not text:
                    continue
                options.append({'value': text, 'label': text})
            overrides.setdefault(group.template_type, {})[group.field_key] = {'options': options}
    except Exception:
        return {}
    return overrides


def _load_template_input_field_overrides() -> dict[str, dict[str, dict[str, object]]]:
    try:
        from .models import TemplateInputField
    except Exception:
        return {}

    overrides: dict[str, dict[str, dict[str, object]]] = {}
    try:
        fields = TemplateInputField.objects.all().only(
            'template_type',
            'field_key',
            'label',
            'input_type',
            'section_title',
            'required',
            'allow_other',
            'other_label',
            'other_placeholder',
            'help_text',
            'textarea_rows',
            'sort_order',
            'is_active',
        )
        for row in fields:
            overrides.setdefault(row.template_type, {})[row.field_key] = {
                'label': row.label,
                'input_type': row.input_type,
                'section_title': row.section_title,
                'required': row.required,
                'allow_other': row.allow_other,
                'other_label': row.other_label,
                'other_placeholder': row.other_placeholder,
                'help_text': row.help_text,
                'textarea_rows': row.textarea_rows,
                'sort_order': row.sort_order,
                'is_active': row.is_active,
            }
    except Exception:
        return {}
    return overrides


def _schema_for_template(
    template_type: str,
    overrides: dict[str, dict[str, object]] | None = None,
    checkbox_option_overrides: dict[str, dict[str, dict[str, object]]] | None = None,
    field_overrides: dict[str, dict[str, dict[str, object]]] | None = None,
) -> list[dict[str, object]]:
    canonical_template_type = _canonical_template_type(template_type)
    schema = TEMPLATE_INPUT_SCHEMAS.get(canonical_template_type, DEFAULT_TEMPLATE_INPUT_SCHEMA)
    merged_fields: list[tuple[int, int, dict[str, object]]] = []
    override_map = (overrides or {}).get(canonical_template_type, {})
    checkbox_override_map = (checkbox_option_overrides or {}).get(canonical_template_type, {})
    field_override_map = (field_overrides or {}).get(canonical_template_type, {})
    base_field_keys = {str(field.get('key') or '') for field in schema}

    for index, base_field in enumerate(schema):
        field = deepcopy(base_field)
        field_key = str(field.get('key') or '')
        base_order = index * 10
        field['sort_order'] = base_order

        field_override = field_override_map.get(field_key)
        override_present = isinstance(field_override, dict)
        skip_checkbox_override = False
        if override_present:
            label = str(field_override.get('label') or '').strip()
            input_type = str(field_override.get('input_type') or '').strip()
            section_title = str(field_override.get('section_title') or '').strip()
            other_label = str(field_override.get('other_label') or '').strip()
            other_placeholder = str(field_override.get('other_placeholder') or '').strip()
            help_text = str(field_override.get('help_text') or '').strip()
            textarea_rows = _normalize_textarea_rows(field_override.get('textarea_rows'), 3)

            if label:
                field['label'] = label
            if input_type:
                field['input_type'] = input_type
            if section_title:
                field['section_title'] = section_title
            field['required'] = bool(field_override.get('required'))
            field['allow_other'] = bool(field_override.get('allow_other'))
            if other_label:
                field['other_label'] = other_label
            if other_placeholder:
                field['other_placeholder'] = other_placeholder
            if help_text:
                field['help_text'] = help_text
            field['textarea_rows'] = textarea_rows
            if field_override.get('sort_order') is not None:
                field['sort_order'] = int(field_override.get('sort_order') or 0)
            if not bool(field_override.get('is_active', True)):
                continue
            if input_type and input_type != 'checkbox_group':
                field.pop('options', None)
                skip_checkbox_override = True

        override = override_map.get(field_key)
        if isinstance(override, dict):
            if 'default_text' in override:
                field['default'] = override.get('default_text', '')
            if override.get('required_override') is not None:
                field['required'] = bool(override.get('required_override'))
        checkbox_override = checkbox_override_map.get(field_key)
        if isinstance(checkbox_override, dict) and not skip_checkbox_override:
            field['options'] = deepcopy(checkbox_override.get('options') or [])
        field.setdefault('input_type', 'textarea')
        merged_fields.append((int(field.get('sort_order') or 0), base_order, field))

    for custom_index, (field_key, field_override) in enumerate(field_override_map.items()):
        if field_key in base_field_keys:
            continue
        if not isinstance(field_override, dict):
            continue
        if not bool(field_override.get('is_active', True)):
            continue

        field: dict[str, object] = {
            'key': field_key,
            'label': str(field_override.get('label') or field_key).strip() or field_key,
            'input_type': str(field_override.get('input_type') or 'textarea').strip() or 'textarea',
            'required': bool(field_override.get('required')),
            'allow_other': bool(field_override.get('allow_other')),
            'other_label': str(field_override.get('other_label') or 'その他'),
            'other_placeholder': str(field_override.get('other_placeholder') or '自由入力'),
            'help_text': str(field_override.get('help_text') or ''),
            'textarea_rows': _normalize_textarea_rows(field_override.get('textarea_rows'), 3),
        }
        sort_order = field_override.get('sort_order')
        field['sort_order'] = int(sort_order if sort_order is not None else ((len(schema) + custom_index) * 10))
        section_title = str(field_override.get('section_title') or '').strip()
        if section_title:
            field['section_title'] = section_title
        override = override_map.get(field_key)
        if isinstance(override, dict):
            if 'default_text' in override:
                field['default'] = override.get('default_text', '')
            if override.get('required_override') is not None:
                field['required'] = bool(override.get('required_override'))
        checkbox_override = checkbox_override_map.get(field_key)
        if isinstance(checkbox_override, dict) and str(field.get('input_type') or 'textarea') == 'checkbox_group':
            field['options'] = deepcopy(checkbox_override.get('options') or [])
        merged_fields.append((int(field.get('sort_order') or 0), len(schema) * 10 + custom_index, field))

    merged_fields.sort(key=lambda item: (item[0], item[1]))
    normalized_fields: list[dict[str, object]] = []
    for field in [field for _sort_order, _base_order, field in merged_fields]:
        field['textarea_rows'] = _normalize_textarea_rows(field.get('textarea_rows'), 3)
        normalized_fields.append(field)
    return normalized_fields


def get_template_input_schema(template_type: str) -> list[dict[str, object]]:
    overrides = _load_template_input_default_overrides()
    checkbox_option_overrides = _load_template_input_checkbox_option_overrides()
    field_overrides = _load_template_input_field_overrides()
    return _schema_for_template(template_type, overrides, checkbox_option_overrides, field_overrides)


def get_template_input_schema_map() -> dict[str, list[dict[str, object]]]:
    overrides = _load_template_input_default_overrides()
    checkbox_option_overrides = _load_template_input_checkbox_option_overrides()
    field_overrides = _load_template_input_field_overrides()
    schema_map: dict[str, list[dict[str, object]]] = {
        template_type: _schema_for_template(template_type, overrides, checkbox_option_overrides, field_overrides)
        for template_type in TEMPLATE_INPUT_SCHEMAS
    }
    for alias in TEMPLATE_INPUT_SCHEMA_ALIASES:
        schema_map[alias] = _schema_for_template(alias, overrides, checkbox_option_overrides, field_overrides)
    schema_map['__default__'] = [deepcopy(field) for field in DEFAULT_TEMPLATE_INPUT_SCHEMA]
    return schema_map
