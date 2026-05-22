from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from anonymizer_app.forms import AnonymizeForm
from anonymizer_app.models import Prompt, RestoreMetadata
from anonymizer_app.structured_input import (
    build_source_input_data,
    build_source_text_from_structured_input,
    build_source_text_from_source_input_data,
    validate_structured_input,
)
from anonymizer_app.template_input_schemas import get_template_input_schema


COMMITTEE_OVERVIEW_DEFAULT = '会議名：\n開催日時：\n開催場所：\n参加者：'


class StructuredInputHelperTests(TestCase):
    def test_build_source_text_from_structured_input_uses_headings(self):
        structured_input = {
            'chief_complaint': '発熱',
            'present_history': '2日前から発熱が持続',
            'past_history': '',
            'admission_purpose': '精査',
            'treatment_plan': '安静と採血',
        }

        source_text = build_source_text_from_structured_input('入院時サマリー', structured_input)

        self.assertIn('【主訴】\n発熱', source_text)
        self.assertIn('【現病歴】\n2日前から発熱が持続', source_text)
        self.assertIn('【入院目的】\n精査', source_text)
        self.assertIn('【治療方針】\n安静と採血', source_text)
        self.assertNotIn('【既往歴】', source_text)
        self.assertEqual(
            build_source_text_from_structured_input('入院時サマリー（詳細版）', structured_input),
            source_text,
        )

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
            'structured__treatment_plan': '安静と採血',
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
        self.assertEqual(prompt.source_input_data['text'], '【主訴】\n発熱\n\n【現病歴】\n2日前から発熱が持続\n\n【入院目的】\n精査\n\n【治療方針】\n安静と採血')
        self.assertEqual(prompt.source_input_data['structured_input']['chief_complaint'], '発熱')
        self.assertEqual(prompt.source_input_data['structured_input']['present_history'], '2日前から発熱が持続')
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
