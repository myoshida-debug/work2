from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.http import QueryDict
from django.test import TestCase, override_settings
from django.urls import reverse

from anonymizer_app.forms import AnonymizeForm
from anonymizer_app.models import (
    Prompt,
    RestoreMetadata,
    TemplateInputCheckboxGroup,
    TemplateInputCheckboxOption,
    TemplateInputDefault,
    TemplateInputField,
)
from anonymizer_app.prompt_template_store import get_template_source_by_name
from anonymizer_app.structured_input import (
    build_source_input_data,
    build_source_text_from_structured_input,
    build_source_text_from_source_input_data,
    collect_structured_input,
    validate_structured_input,
)
from anonymizer_app.template_input_schemas import get_template_input_schema, get_template_input_schema_map
from anonymizer.modules.anonymize import anonymize_text


COMMITTEE_OVERVIEW_DEFAULT = '会議名：\n開催日時：\n開催場所：\n参加者：'


class StructuredInputHelperTests(TestCase):
    def test_build_source_text_from_structured_input_uses_headings(self):
        structured_input = {
            'chief_complaint': '発熱',
            'present_history': '2日前から発熱が持続',
            'past_history': '',
            'admission_purpose': '精査',
            'treatment_plan': {
                'selected': ['安静', '輸液'],
                'other': '必要時鎮痛薬',
                'other_checked': True,
            },
        }

        source_text = build_source_text_from_structured_input('入院時サマリー', structured_input)

        self.assertIn('【主訴】\n発熱', source_text)
        self.assertIn('【現病歴】\n2日前から発熱が持続', source_text)
        self.assertIn('【入院目的】\n精査', source_text)
        self.assertIn('【治療方針】\n・安静\n・輸液\n・その他: 必要時鎮痛薬', source_text)
        self.assertNotIn('【既往歴】', source_text)
        self.assertEqual(
            build_source_text_from_structured_input('入院時サマリー（詳細版）', structured_input),
            source_text,
        )

    def test_build_source_text_from_structured_input_prefers_text_over_checkbox_selection(self):
        structured_input = {
            'treatment_plan': {
                'text': '独自記載',
                'selected': ['安静', '輸液'],
                'other': '',
                'other_checked': False,
            },
        }

        source_text = build_source_text_from_structured_input('入院時サマリー', structured_input)

        self.assertIn('【治療方針】\n独自記載', source_text)
        self.assertNotIn('・安静', source_text)

    def test_collect_structured_input_supports_checkbox_group_and_other(self):
        post_data = QueryDict('', mutable=True)
        post_data.update({
            'structured__chief_complaint': '発熱',
            'structured__present_history': '2日前から発熱が持続',
            'structured__admission_purpose': '精査',
            'structured__treatment_plan__other': '必要時鎮痛薬',
            'structured__treatment_plan__other_checked': '1',
        })
        post_data.setlist('structured__treatment_plan', ['安静', '輸液'])

        structured_input = collect_structured_input('入院時サマリー', post_data)

        self.assertEqual(structured_input['treatment_plan']['selected'], ['安静', '輸液'])
        self.assertEqual(structured_input['treatment_plan']['other'], '必要時鎮痛薬')
        self.assertTrue(structured_input['treatment_plan']['other_checked'])

    def test_treatment_plan_schema_uses_checkbox_group(self):
        schema = get_template_input_schema('入院時サマリー')
        treatment_plan = next(field for field in schema if field['key'] == 'treatment_plan')

        self.assertEqual(treatment_plan.get('input_type'), 'checkbox_group')
        self.assertTrue(treatment_plan.get('allow_other'))
        self.assertGreaterEqual(len(treatment_plan.get('options') or []), 3)

    def test_psychiatric_admission_schema_uses_master_checkbox_groups(self):
        schema = get_template_input_schema('精神科入院時サマリー')

        admission_type = next(field for field in schema if field['key'] == 'admission_type')
        psych_symptoms = next(field for field in schema if field['key'] == 'psych_symptoms')
        admission_purpose_safety = next(field for field in schema if field['key'] == 'admission_purpose_safety')
        treatment_policy_multidisciplinary = next(field for field in schema if field['key'] == 'treatment_policy_multidisciplinary')
        discharge_goal = next(field for field in schema if field['key'] == 'discharge_goal')

        self.assertEqual(admission_type.get('input_type'), 'checkbox_group')
        self.assertEqual(admission_type.get('section_title'), '入院形態')
        self.assertEqual([option['value'] for option in admission_type.get('options') or []], [
            'ADM001',
            'ADM002',
            'ADM003',
            'ADM004',
            'ADM005',
        ])
        self.assertEqual(psych_symptoms.get('input_type'), 'checkbox_group')
        self.assertEqual(psych_symptoms.get('section_title'), '① 主訴（患者・家族が訴える主な問題）')
        self.assertGreaterEqual(len(psych_symptoms.get('options') or []), 10)
        self.assertEqual([option['value'] for option in admission_purpose_safety.get('options') or []], [
            'GOAL009',
            'GOAL010',
            'GOAL011',
            'GOAL012',
            'GOAL013',
            'GOAL014',
        ])
        self.assertEqual([option['value'] for option in treatment_policy_multidisciplinary.get('options') or []], [
            'PLAN028',
            'PLAN029',
            'PLAN030',
            'PLAN031',
            'PLAN032',
            'PLAN033',
            'PLAN034',
        ])
        self.assertTrue(discharge_goal.get('required'))

    def test_psychiatric_discharge_doctor_schema_uses_choice_groups(self):
        schema = get_template_input_schema('精神科退院時サマリー（医師用）')

        discharge_date = next(field for field in schema if field['key'] == 'discharge_date')
        discharge_destination = next(field for field in schema if field['key'] == 'discharge_destination')
        admission_type = next(field for field in schema if field['key'] == 'admission_type')
        adl = next(field for field in schema if field['key'] == 'adl')
        risk_suicide = next(field for field in schema if field['key'] == 'risk_suicide')
        post_discharge_policy = next(field for field in schema if field['key'] == 'post_discharge_policy')

        self.assertEqual(discharge_date.get('input_type'), 'date')
        self.assertEqual(discharge_destination.get('input_type'), 'checkbox_group')
        self.assertFalse(discharge_destination.get('allow_other'))
        self.assertEqual([option['label'] for option in discharge_destination.get('options') or []], [
            '自宅',
            '家族宅',
            '施設',
            '転院',
            'その他',
        ])
        self.assertEqual(admission_type.get('input_type'), 'checkbox_group')
        self.assertFalse(admission_type.get('allow_other'))
        self.assertEqual([option['label'] for option in adl.get('options') or []], [
            '自立',
            '一部介助',
            '全介助',
        ])
        self.assertEqual([option['label'] for option in risk_suicide.get('options') or []], ['あり', 'なし'])
        self.assertEqual(post_discharge_policy.get('section_title'), '4. 退院後方針')

    def test_date_fields_use_date_input_type(self):
        doctor = get_template_input_schema('精神科退院時サマリー（医師用）')
        nursing_admission = get_template_input_schema('看護入院時サマリー')
        nursing_midterm = get_template_input_schema('看護中間サマリー')
        nursing_discharge = get_template_input_schema('看護退院時サマリー')
        ot_summary = get_template_input_schema('OT評価サマリー')
        psw_summary = get_template_input_schema('PSW退院支援サマリー')
        home_nursing = get_template_input_schema('精神科訪問看護サマリー')

        self.assertEqual(next(field for field in doctor if field['key'] == 'discharge_date')['input_type'], 'date')
        self.assertEqual(next(field for field in nursing_admission if field['key'] == 'admission_date')['input_type'], 'date')
        self.assertEqual(next(field for field in nursing_midterm if field['key'] == 'created_date')['input_type'], 'date')
        self.assertEqual(next(field for field in nursing_discharge if field['key'] == 'discharge_date')['input_type'], 'date')
        self.assertEqual(next(field for field in ot_summary if field['key'] == 'evaluation_date')['input_type'], 'date')
        self.assertEqual(next(field for field in psw_summary if field['key'] == 'created_date')['input_type'], 'date')
        self.assertEqual(next(field for field in psw_summary if field['key'] == 'planned_discharge_date')['input_type'], 'date')
        self.assertEqual(next(field for field in home_nursing if field['key'] == 'created_date')['input_type'], 'date')

    def test_treatment_plan_schema_uses_db_checkbox_options(self):
        group = TemplateInputCheckboxGroup.objects.get(
            template_type='入院時サマリー',
            field_key='treatment_plan',
        )
        group.options.all().delete()
        TemplateInputCheckboxOption.objects.create(group=group, text='安静(更新)', sort_order=0)
        TemplateInputCheckboxOption.objects.create(group=group, text='リハビリ強化', sort_order=10)

        schema = get_template_input_schema('入院時サマリー')
        treatment_plan = next(field for field in schema if field['key'] == 'treatment_plan')

        self.assertEqual(
            [option['value'] for option in treatment_plan.get('options') or []],
            ['安静(更新)', 'リハビリ強化'],
        )

    def test_non_checkbox_field_schema_uses_db_checkbox_options(self):
        group = TemplateInputCheckboxGroup.objects.create(
            template_type='委員会議事録',
            field_key='agenda',
        )
        TemplateInputCheckboxOption.objects.create(group=group, text='検討事項', sort_order=0)
        TemplateInputCheckboxOption.objects.create(group=group, text='共有事項', sort_order=10)

        schema = get_template_input_schema('委員会議事録')
        agenda = next(field for field in schema if field['key'] == 'agenda')

        self.assertEqual(agenda.get('input_type'), 'textarea')
        self.assertEqual(
            [option['value'] for option in agenda.get('options') or []],
            ['検討事項', '共有事項'],
        )

    def test_template_input_field_schema_adds_custom_fields_and_reorders_existing_fields(self):
        TemplateInputField.objects.create(
            template_type='委員会議事録',
            field_key='custom_note',
            label='自由メモ',
            input_type='textarea',
            textarea_rows=7,
            sort_order=0,
            section_title='補足',
        )
        TemplateInputField.objects.create(
            template_type='委員会議事録',
            field_key='overview',
            label='開催情報',
            input_type='textarea',
            required=True,
            textarea_rows=5,
            sort_order=30,
        )

        schema = get_template_input_schema('委員会議事録')

        self.assertEqual(schema[0]['key'], 'custom_note')
        self.assertEqual(schema[0]['label'], '自由メモ')
        self.assertEqual(schema[0]['section_title'], '補足')
        self.assertEqual(schema[0]['textarea_rows'], 7)
        overview = next(field for field in schema if field['key'] == 'overview')
        self.assertEqual(overview['label'], '開催情報')
        self.assertEqual(overview['sort_order'], 30)
        self.assertEqual(overview['input_type'], 'textarea')
        self.assertEqual(overview['textarea_rows'], 5)

    def test_template_input_field_schema_can_hide_and_retype_fields(self):
        TemplateInputField.objects.create(
            template_type='入院時サマリー',
            field_key='treatment_plan',
            label='治療内容',
            input_type='textarea',
            sort_order=5,
            is_active=True,
        )
        TemplateInputField.objects.create(
            template_type='入院時サマリー',
            field_key='admission_purpose',
            is_active=False,
            sort_order=15,
        )

        schema = get_template_input_schema('入院時サマリー')

        treatment_plan = next(field for field in schema if field['key'] == 'treatment_plan')
        self.assertEqual(treatment_plan['label'], '治療内容')
        self.assertEqual(treatment_plan['input_type'], 'textarea')
        self.assertFalse(treatment_plan.get('options'))
        self.assertNotIn('admission_purpose', [field['key'] for field in schema])

    def test_validate_structured_input_flags_missing_required_fields(self):
        errors = validate_structured_input('入院時サマリー', {'chief_complaint': '発熱'})

        self.assertIn('present_history', errors)
        self.assertIn('admission_purpose', errors)
        self.assertIn('treatment_plan', errors)
        self.assertIn('必須項目です', errors['present_history'])

    def test_committee_overview_schema_has_default_text(self):
        schema = get_template_input_schema('委員会議事録')
        overview = next(field for field in schema if field['key'] == 'overview')

        self.assertEqual(overview.get('default'), COMMITTEE_OVERVIEW_DEFAULT)

    def test_committee_overview_schema_uses_db_override(self):
        TemplateInputDefault.objects.create(
            template_type='委員会議事録',
            field_key='overview',
            default_text='会議名：\n開催日時：\n参加者：',
        )

        schema = get_template_input_schema('委員会議事録')
        overview = next(field for field in schema if field['key'] == 'overview')

        self.assertEqual(overview.get('default'), '会議名：\n開催日時：\n参加者：')

    def test_committee_overview_schema_uses_required_override(self):
        TemplateInputDefault.objects.create(
            template_type='委員会議事録',
            field_key='overview',
            required_override=False,
        )

        schema = get_template_input_schema('委員会議事録')
        overview = next(field for field in schema if field['key'] == 'overview')

        self.assertFalse(overview.get('required'))

    def test_template_input_schema_map_includes_aliases(self):
        schema_map = get_template_input_schema_map()

        self.assertIn('入院時サマリー（詳細版）', schema_map)
        self.assertIn('精神科入院時サマリー', schema_map)
        self.assertIn('OT評価サマリー', schema_map)
        self.assertIn('PSW退院支援サマリー', schema_map)
        self.assertIn('精神科訪問看護サマリー', schema_map)
        self.assertIn('インシデントレポート（様式1-3）', schema_map)
        self.assertIn('インシデントレポート（簡易版）', schema_map)

    def test_psychiatric_admission_template_source_is_registered(self):
        source = get_template_source_by_name('精神科入院時サマリー')

        self.assertIsNotNone(source)
        self.assertEqual(source.template_type, '精神科入院時サマリー')
        self.assertIn('## 入院形態', source.content)
        self.assertIn('## ① 主訴（患者・家族が訴える主な問題）', source.content)
        self.assertIn('### 精神症状', source.content)
        self.assertIn('## ③ 治療方針', source.content)

    def test_new_nursing_template_sources_are_registered(self):
        self.assertIsNotNone(get_template_source_by_name('精神科退院時サマリー（医師用）'))
        self.assertIsNotNone(get_template_source_by_name('看護入院時サマリー'))
        self.assertIsNotNone(get_template_source_by_name('看護中間サマリー'))
        self.assertIsNotNone(get_template_source_by_name('看護退院時サマリー'))

        source = get_template_source_by_name('看護退院時サマリー')
        self.assertIsNotNone(source)
        self.assertIn('## 1. 退院時状態', source.content)
        self.assertIn('## 4. 看護評価', source.content)

    def test_new_ot_psw_and_home_nursing_template_sources_are_registered(self):
        ot_source = get_template_source_by_name('OT評価サマリー')
        psw_source = get_template_source_by_name('PSW退院支援サマリー')
        home_nursing_source = get_template_source_by_name('精神科訪問看護サマリー')

        self.assertIsNotNone(ot_source)
        self.assertIsNotNone(psw_source)
        self.assertIsNotNone(home_nursing_source)
        self.assertIn('## 1. OT導入目的', ot_source.content)
        self.assertIn('## 8. 総合評価・自由記載', ot_source.content)
        self.assertIn('## 1. 退院支援開始理由', psw_source.content)
        self.assertIn('## 8. 総合評価・引き継ぎ事項', psw_source.content)
        self.assertIn('## 6. リスク評価', home_nursing_source.content)
        self.assertIn('## 9. 総合評価・申し送り', home_nursing_source.content)

    def test_ot_psw_and_home_nursing_schemas_use_master_codes(self):
        ot_schema = get_template_input_schema('OT評価サマリー')
        psw_schema = get_template_input_schema('PSW退院支援サマリー')
        home_nursing_schema = get_template_input_schema('精神科訪問看護サマリー')

        ot_purpose = next(field for field in ot_schema if field['key'] == 'ot_purpose')
        activity_participation = next(field for field in ot_schema if field['key'] == 'activity_participation')
        work_understanding = next(field for field in ot_schema if field['key'] == 'work_understanding')
        psw_destination = next(field for field in psw_schema if field['key'] == 'discharge_destination')
        psw_conference = next(field for field in psw_schema if field['key'] == 'discharge_conference')
        home_visit_frequency = next(field for field in home_nursing_schema if field['key'] == 'visit_frequency')
        home_risk_suicide = next(field for field in home_nursing_schema if field['key'] == 'risk_suicide')
        home_support_content = next(field for field in home_nursing_schema if field['key'] == 'support_content')

        self.assertEqual([option['value'] for option in ot_purpose.get('options') or []], [
            'OTG001',
            'OTG002',
            'OTG003',
            'OTG004',
            'OTG005',
            'OTG006',
            'OTG007',
            'OTG008',
            'OTG009',
            'OTG010',
        ])
        self.assertEqual([option['value'] for option in activity_participation.get('options') or []], [
            'OTP001',
            'OTP002',
            'OTP003',
            'OTP004',
            'OTP005',
            'OTP006',
            'OTP007',
        ])
        self.assertEqual([option['value'] for option in work_understanding.get('options') or []], [
            'OTW001',
            'OTW002',
            'OTW003',
        ])
        self.assertEqual([option['value'] for option in psw_destination.get('options') or []], [
            'PSWD001',
            'PSWD002',
            'PSWD003',
            'PSWD004',
            'PSWD005',
            'PSWD006',
        ])
        self.assertEqual([option['value'] for option in psw_conference.get('options') or []], [
            'PSWC001',
            'PSWC002',
            'PSWC003',
            'PSWC004',
            'PSWC005',
            'PSWC006',
            'PSWC007',
            'PSWC008',
            'PSWC009',
            'PSWC010',
        ])
        self.assertEqual([option['value'] for option in home_visit_frequency.get('options') or []], [
            'HVF001',
            'HVF002',
            'HVF003',
            'HVF004',
        ])
        self.assertEqual([option['value'] for option in home_risk_suicide.get('options') or []], [
            'HVR001',
            'HVR002',
        ])
        self.assertEqual([option['value'] for option in home_support_content.get('options') or []], [
            'SUPH001',
            'SUPH002',
            'SUPH003',
            'SUPH004',
            'SUPH005',
            'SUPH006',
            'SUPH007',
            'SUPH008',
            'SUPH009',
            'SUPH010',
        ])

    def test_build_source_text_from_structured_input_supports_ot_evaluation(self):
        structured_input = {
            'evaluation_date': '2026-05-01',
            'evaluator': 'OTA',
            'ward': '精神科病棟',
            'attending_physician': '医師A',
            'participation_form': {'selected': ['OTF001']},
            'ot_purpose': {'selected': ['OTG001', 'OTG003']},
            'activity_participation': {'selected': ['OTP001', 'OTP006']},
            'work_understanding': {'selected': ['OTW001']},
            'work_concentration': {'selected': ['OTW002']},
            'overall_evaluation': '継続評価が必要。',
        }

        source_text = build_source_text_from_structured_input('OT評価サマリー', structured_input)

        self.assertIn('## 基本情報', source_text)
        self.assertIn('### 参加形態\n・個別', source_text)
        self.assertIn('## 1. OT導入目的', source_text)
        self.assertIn('・生活リズム改善', source_text)
        self.assertIn('## 3. 作業遂行能力', source_text)
        self.assertIn('### 理解力\n・良好', source_text)
        self.assertIn('## 8. 総合評価・自由記載', source_text)
        self.assertIn('継続評価が必要。', source_text)

    def test_build_source_input_data_keeps_source_payload(self):
        payload = build_source_input_data(
            '委員会議事録',
            'structured',
            f'【開催概要】\n{COMMITTEE_OVERVIEW_DEFAULT}',
            {'overview': COMMITTEE_OVERVIEW_DEFAULT, 'agenda': '検討'},
        )

        self.assertEqual(payload['template_type'], '委員会議事録')
        self.assertEqual(payload['input_mode'], 'structured')
        self.assertEqual(payload['text'], f'【開催概要】\n{COMMITTEE_OVERVIEW_DEFAULT}')
        self.assertEqual(payload['structured_input']['overview'], COMMITTEE_OVERVIEW_DEFAULT)
        self.assertEqual(payload['structured_input']['agenda'], '検討')

    def test_build_source_input_data_keeps_voice_transcript_source(self):
        payload = build_source_input_data(
            '看護計画',
            'voice',
            '患者は安静を保っている',
            transcript_source='browser_recording',
        )

        self.assertEqual(payload['template_type'], '看護計画')
        self.assertEqual(payload['input_mode'], 'voice')
        self.assertEqual(payload['text'], '患者は安静を保っている')
        self.assertEqual(payload['structured_input'], {})
        self.assertEqual(payload['transcript_source'], 'browser_recording')

    def test_build_source_text_from_source_input_data_uses_structured_payload(self):
        payload = build_source_input_data(
            '委員会議事録',
            'structured',
            '',
            {'overview': COMMITTEE_OVERVIEW_DEFAULT, 'agenda': '検討'},
        )

        source_text = build_source_text_from_source_input_data(payload)

        self.assertIn(f'【開催概要】\n{COMMITTEE_OVERVIEW_DEFAULT}', source_text)
        self.assertIn('【議題】\n検討', source_text)

    def test_collect_structured_input_uses_master_codes_for_psychiatric_admission(self):
        post_data = QueryDict('', mutable=True)
        post_data.update({
            'structured__basic_info': '入院時評価',
            'structured__discharge_goal': '退院後も通院と服薬を継続する',
        })
        post_data.setlist('structured__admission_type', ['ADM002'])
        post_data.setlist('structured__psych_symptoms', ['PSY006', 'PSY012'])
        post_data.setlist('structured__life_issues', ['LIF007'])
        post_data.setlist('structured__physical_dependency', ['PHY005'])
        post_data.setlist('structured__admission_purpose_safety', ['GOAL009', 'GOAL012'])
        post_data.setlist('structured__admission_purpose_treatment_introduction', ['GOAL015'])
        post_data.setlist('structured__treatment_policy_nursing', ['PLAN015'])
        post_data.setlist('structured__treatment_policy_multidisciplinary', ['PLAN028', 'PLAN029'])
        post_data.setlist('structured__risk_assessment', ['RISK003'])
        post_data.setlist('structured__behavior_restrictions', ['ACT004'])
        post_data.setlist('structured__discharge_support_tasks', ['DIS002'])

        structured_input = collect_structured_input('精神科入院時サマリー', post_data)

        self.assertEqual(structured_input['admission_type']['selected'], ['ADM002'])
        self.assertEqual(structured_input['psych_symptoms']['selected'], ['PSY006', 'PSY012'])
        self.assertEqual(structured_input['admission_purpose_safety']['selected'], ['GOAL009', 'GOAL012'])
        self.assertEqual(structured_input['treatment_policy_multidisciplinary']['selected'], ['PLAN028', 'PLAN029'])
        self.assertEqual(structured_input['discharge_support_tasks']['selected'], ['DIS002'])

    def test_build_source_text_from_structured_input_supports_psychiatric_admission(self):
        structured_input = {
            'admission_type': {
                'selected': ['ADM002'],
            },
            'psych_symptoms': {
                'selected': ['PSY006', 'PSY012'],
            },
            'admission_purpose_safety': {
                'selected': ['GOAL009', 'GOAL012'],
            },
            'treatment_policy_nursing': {
                'selected': ['PLAN015'],
            },
            'treatment_policy_multidisciplinary': {
                'selected': ['PLAN028', 'PLAN029'],
            },
            'behavior_restrictions': {
                'selected': ['ACT004'],
            },
            'risk_assessment': {
                'selected': ['RISK003'],
            },
            'discharge_support_tasks': {
                'selected': ['DIS002'],
            },
            'discharge_goal': '退院後も通院と服薬を継続する',
        }

        source_text = build_source_text_from_structured_input('精神科入院時サマリー', structured_input)

        self.assertIn('## 入院形態\n\n・医療保護入院', source_text)
        self.assertIn('## ① 主訴（患者・家族が訴える主な問題）', source_text)
        self.assertIn('### 精神症状\n・幻覚\n・病識欠如', source_text)
        self.assertIn('## ② 入院目的', source_text)
        self.assertIn('### 安全確保\n・本人保護\n・行動制限下での治療', source_text)
        self.assertIn('## ③ 治療方針', source_text)
        self.assertIn('### 看護・行動観察\n・行動観察強化', source_text)
        self.assertIn('### 多職種・地域連携\n・PSW介入\n・訪問看護調整', source_text)
        self.assertIn('## リスク評価\n\n・他害リスク', source_text)
        self.assertIn('## 退院支援課題\n\n・服薬継続困難', source_text)
        self.assertIn('## 退院目標\n\n退院後も通院と服薬を継続する', source_text)

    def test_build_source_text_from_structured_input_supports_psychiatric_discharge_doctor(self):
        structured_input = {
            'discharge_date': '2025-05-01',
            'hospitalization_period': '2025-03-01〜2025-05-01',
            'ward': '精神科病棟',
            'attending_physician': '医師A',
            'discharge_destination': {'selected': ['DDO001']},
            'admission_type': {'selected': ['DDA002']},
            'main_symptoms': {'selected': ['DDS001', 'DDS002']},
            'treatment_content': {'selected': ['DDT001', 'DDT007']},
            'course': '症状は徐々に軽快した。',
            'mental_state': {'selected': ['DDS001']},
            'adl': {'selected': ['DAD001']},
            'risk_suicide': {'selected': ['DRK002']},
            'risk_harm': {'selected': ['DRK002']},
            'risk_leave_hospital': {'selected': ['DRK002']},
            'risk_relapse': {'selected': ['DRK001']},
            'post_discharge_policy': {'selected': ['DDP001', 'DDP002']},
        }

        source_text = build_source_text_from_structured_input('精神科退院時サマリー（医師用）', structured_input)

        self.assertIn('## 基本情報', source_text)
        self.assertIn('### 退院先\n・自宅', source_text)
        self.assertIn('## 1. 入院時主症状', source_text)
        self.assertIn('### 精神症状\n・幻覚妄想\n・希死念慮', source_text)
        self.assertIn('## 2. 入院後経過', source_text)
        self.assertIn('### 経過\n症状は徐々に軽快した。', source_text)
        self.assertIn('## 3. 退院時状態', source_text)
        self.assertIn('### ADL\n・自立', source_text)
        self.assertIn('### 再発リスク\n・あり', source_text)
        self.assertIn('## 4. 退院後方針', source_text)

    def test_anonymize_text_uses_halfwidth_parentheses_in_time_labels(self):
        result = anonymize_text('2月中旬午後3時に来院した。')

        self.assertIn('午後(時刻1)', result.text)
        self.assertNotIn('午後（時刻1）', result.text)
        self.assertIn('午後(時刻1)', result.restore_map)
        self.assertEqual(result.restore_map['午後(時刻1)'], '午後3時')


@override_settings(ALLOWED_HOSTS=['testserver'], NETWORK_POLICY_ENFORCED=False)
class StructuredInputViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='close_user',
            password='pass12345',
        )
        self.client.force_login(self.user)

    def test_home_post_structured_mode_creates_prompt_without_raw_structured_input(self):
        template_name = next(
            value
            for value, _label in AnonymizeForm().fields['template'].choices
            if value.startswith('入院時サマリー')
        )
        post_data = {
            'template': template_name,
            'input_mode': 'structured',
            'structured__chief_complaint': '発熱',
            'structured__present_history': '2日前から発熱が持続',
            'structured__admission_purpose': '精査',
            'structured__treatment_plan': ['安静', '輸液'],
            'structured__treatment_plan__other_checked': '1',
            'structured__treatment_plan__other': '必要時鎮痛薬',
        }

        with patch(
            'close_side.views.anonymize_text',
            return_value=SimpleNamespace(
                text='匿名化済み本文',
                restore_map={'患者A': '山田太郎'},
            ),
        ):
            response = self.client.post(reverse('close_side:home'), post_data)

        self.assertEqual(response.status_code, 200)

        metadata = RestoreMetadata.objects.get(owner=self.user)
        prompt = Prompt.objects.get(source_id=metadata.source_id)
        payload = metadata.prompt_json
        payload_dump = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(payload['content']['text'], '匿名化済み本文')
        self.assertEqual(payload['metadata']['input_mode'], 'structured')
        self.assertEqual(
            payload['metadata']['structured_input_labels'],
            ['主訴', '現病歴', '入院目的', '治療方針'],
        )
        self.assertEqual(metadata.prompt_json['metadata']['input_mode'], 'structured')
        self.assertEqual(prompt.source_input_data['template_type'], template_name)
        self.assertEqual(prompt.source_input_data['input_mode'], 'structured')
        self.assertEqual(
            prompt.source_input_data['text'],
            '【主訴】\n発熱\n\n【現病歴】\n2日前から発熱が持続\n\n【入院目的】\n精査\n\n【治療方針】\n・安静\n・輸液\n・その他: 必要時鎮痛薬',
        )
        self.assertEqual(prompt.source_input_data['structured_input']['chief_complaint'], '発熱')
        self.assertEqual(prompt.source_input_data['structured_input']['present_history'], '2日前から発熱が持続')
        self.assertEqual(prompt.source_input_data['structured_input']['treatment_plan']['selected'], ['安静', '輸液'])
        self.assertEqual(prompt.source_input_data['structured_input']['treatment_plan']['other'], '必要時鎮痛薬')
        self.assertEqual(prompt.content, metadata.prompt_json['prompt_text'])
        self.assertNotIn('発熱', payload_dump)
        self.assertNotIn('2日前から発熱が持続', payload_dump)
        self.assertNotIn('精査', payload_dump)
        self.assertNotIn('安静と採血', payload_dump)

    def test_home_post_voice_mode_creates_prompt_from_transcript_text(self):
        template_name = '看護計画'
        post_data = {
            'template': template_name,
            'input_mode': 'voice',
            'transcript_text': '患者は安静を保っている',
            'transcript_source': 'browser_recording',
        }

        with patch(
            'close_side.views.anonymize_text',
            return_value=SimpleNamespace(
                text='匿名化済み本文',
                restore_map={'患者A': '山田太郎'},
            ),
        ):
            response = self.client.post(reverse('close_side:home'), post_data)

        self.assertEqual(response.status_code, 200)

        metadata = RestoreMetadata.objects.get(owner=self.user)
        prompt = Prompt.objects.get(source_id=metadata.source_id)
        payload = metadata.prompt_json

        self.assertEqual(payload['metadata']['input_mode'], 'voice')
        self.assertNotIn('transcript_source', payload['metadata'])
        self.assertEqual(payload['content']['text'], '匿名化済み本文')
        self.assertEqual(prompt.source_input_data['input_mode'], 'voice')
        self.assertEqual(prompt.source_input_data['text'], '患者は安静を保っている')
        self.assertEqual(prompt.source_input_data['transcript_source'], 'browser_recording')
        self.assertEqual(prompt.content, metadata.prompt_json['prompt_text'])

    def test_home_post_voice_mode_requires_transcript_text(self):
        post_data = {
            'template': '看護計画',
            'input_mode': 'voice',
            'transcript_text': '',
            'transcript_source': 'manual_input',
        }

        response = self.client.post(reverse('close_side:home'), post_data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '文字起こし結果が空です。録音または入力してください。')
        self.assertFalse(RestoreMetadata.objects.exists())

    def test_prompts_list_shows_reload_button_for_saved_source_data(self):
        prompt = Prompt.objects.create(
            name='委員会議事録 / reload',
            content='prompt body',
            source_input_data={
                'template_type': '委員会議事録',
                'input_mode': 'structured',
                'text': f'【開催概要】\n{COMMITTEE_OVERVIEW_DEFAULT}',
                'structured_input': {
                    'overview': COMMITTEE_OVERVIEW_DEFAULT,
                    'agenda': '議題A',
                },
            },
            source_id='prompt_reload_1234',
            owner=self.user,
        )

        response = self.client.get(reverse('close_side:prompts_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '再読み込み')
        self.assertContains(response, COMMITTEE_OVERVIEW_DEFAULT)
        self.assertContains(response, f'reload_prompt_id={prompt.pk}')

    def test_home_get_reload_prompt_prefills_saved_source_data(self):
        prompt = Prompt.objects.create(
            name='委員会議事録 / reload',
            content='prompt body',
            source_input_data={
                'template_type': '委員会議事録',
                'input_mode': 'structured',
                'text': f'【開催概要】\n{COMMITTEE_OVERVIEW_DEFAULT}',
                'structured_input': {
                    'overview': COMMITTEE_OVERVIEW_DEFAULT,
                    'agenda': '議題A',
                },
            },
            source_id='prompt_reload_5678',
            owner=self.user,
        )

        response = self.client.get(reverse('close_side:home'), {'reload_prompt_id': prompt.pk})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['template_type'], '委員会議事録')
        self.assertEqual(response.context['input_mode'], 'structured')
        self.assertEqual(response.context['source_text'], f'【開催概要】\n{COMMITTEE_OVERVIEW_DEFAULT}')
        overview = next(field for field in response.context['structured_fields'] if field['key'] == 'overview')
        agenda = next(field for field in response.context['structured_fields'] if field['key'] == 'agenda')
        self.assertEqual(overview['value'], COMMITTEE_OVERVIEW_DEFAULT)
        self.assertEqual(agenda['value'], '議題A')

    def test_home_get_uses_custom_textarea_rows_for_structured_fields(self):
        TemplateInputField.objects.create(
            template_type='委員会議事録',
            field_key='overview',
            label='開催概要',
            input_type='textarea',
            textarea_rows=6,
            sort_order=0,
        )
        prompt = Prompt.objects.create(
            name='委員会議事録 / size',
            content='prompt body',
            source_input_data={
                'template_type': '委員会議事録',
                'input_mode': 'structured',
                'text': f'【開催概要】\n{COMMITTEE_OVERVIEW_DEFAULT}',
                'structured_input': {
                    'overview': COMMITTEE_OVERVIEW_DEFAULT,
                },
            },
            source_id='prompt_size_rows_1234',
            owner=self.user,
        )

        response = self.client.get(reverse('close_side:home'), {'reload_prompt_id': prompt.pk})

        self.assertEqual(response.status_code, 200)
        overview = next(field for field in response.context['structured_fields'] if field['key'] == 'overview')
        self.assertEqual(overview['textarea_rows'], 6)
        self.assertContains(response, 'rows="6"')
        self.assertContains(response, 'min-height: calc(6 * 1.65em + 24px);')

    def test_home_post_structured_mode_renders_checkbox_options_once(self):
        template_name = '入院時サマリー'

        response = self.client.post(reverse('close_side:home'), {
            'template': template_name,
            'input_mode': 'structured',
        })

        self.assertEqual(response.status_code, 200)
        treatment_plan = next(field for field in get_template_input_schema(template_name) if field['key'] == 'treatment_plan')
        expected_count = len(treatment_plan.get('options') or [])
        self.assertEqual(response.content.count(b'name="structured__treatment_plan"'), expected_count)

    def test_update_prompt_payload_returns_refreshed_compare_html(self):
        source_id = 'prompt_compare_1234'
        RestoreMetadata.objects.create(
            source_id=source_id,
            template_type='委員会議事録',
            restore_map={'患者A': '山田太郎'},
            prompt_json={'metadata': {'input_mode': 'free'}},
            owner=self.user,
        )

        response = self.client.post(
            reverse('close_side:update_prompt_payload'),
            data=json.dumps({
                'source_id': source_id,
                'template_type': '委員会議事録',
                'input_mode': 'free',
                'source_text': '山田太郎が来院した',
                'structured_input': {},
                'structured_input_labels': [],
                'anonymized_text': '患者Aが来院した',
                'restore_map': {'患者A': '山田太郎'},
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertIn('compare_original_html', payload)
        self.assertIn('compare_anonymized_html', payload)
        self.assertIn('class="anonymized-label changed"', payload['compare_original_html'])
        self.assertIn('山田太郎', payload['compare_original_html'])
        self.assertIn('class="anonymized-label changed"', payload['compare_anonymized_html'])
        self.assertIn('患者A', payload['compare_anonymized_html'])

    def test_committee_overview_context_uses_default_text(self):
        from close_side.views import _structured_field_context

        fields = _structured_field_context('委員会議事録')
        overview = next(field for field in fields if field['key'] == 'overview')

        self.assertEqual(overview['value'], COMMITTEE_OVERVIEW_DEFAULT)

    def test_committee_overview_context_keeps_explicit_blank_value(self):
        from close_side.views import _structured_field_context

        fields = _structured_field_context('委員会議事録', {'overview': ''})
        overview = next(field for field in fields if field['key'] == 'overview')

        self.assertEqual(overview['value'], '')
