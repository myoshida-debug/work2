from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from datetime import date
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from anonymizer_app.models import (
    Patient,
    Prompt,
    RestoreMetadata,
    RestoredResult,
    TemplateInputCheckboxGroup,
    TemplateInputCheckboxOption,
    TemplateInputDefault,
    TemplateInputField,
)
from anonymizer_app.template_input_schemas import get_template_input_schema


@override_settings(ALLOWED_HOSTS=['testserver'], NETWORK_POLICY_ENFORCED=False)
class TranscriptionApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='close_user',
            password='pass12345',
        )
        self.client.force_login(self.user)

    def test_transcribe_audio_returns_text_and_source(self):
        audio_file = SimpleUploadedFile(
            'voice.webm',
            b'fake audio bytes',
            content_type='audio/webm',
        )

        with patch(
            'close_side.views.transcribe_audio_file',
            return_value={'text': '患者は安静を保っている', 'model': 'gpt-4o-transcribe'},
        ) as mocked_transcribe:
            response = self.client.post(
                reverse('close_side:transcribe_audio'),
                data={
                    'audio_file': audio_file,
                    'template_type': '看護計画',
                    'transcript_source': 'browser_recording',
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload['text'], '患者は安静を保っている')
        self.assertEqual(payload['model'], 'gpt-4o-transcribe')
        self.assertEqual(payload['transcript_source'], 'browser_recording')
        mocked_transcribe.assert_called_once()
        self.assertEqual(mocked_transcribe.call_args.kwargs['template_type'], '看護計画')

    def test_transcribe_audio_file_uses_local_whisper_model(self):
        audio_file = SimpleUploadedFile(
            'voice.webm',
            b'fake audio bytes',
            content_type='audio/webm',
        )
        fake_model = MagicMock()
        fake_model.transcribe.return_value = (
            [SimpleNamespace(text='患者は安静を保っている')],
            SimpleNamespace(language='ja'),
        )

        with patch('close_side.transcription._load_whisper_model', return_value=fake_model) as mocked_load:
            from close_side.transcription import transcribe_audio_file

            result = transcribe_audio_file(audio_file, template_type='看護計画')

        self.assertEqual(result['text'], '患者は安静を保っている')
        self.assertEqual(result['model'], 'small')
        self.assertEqual(result['language'], 'ja')
        mocked_load.assert_called_once()
        fake_model.transcribe.assert_called_once()
        transcribe_path = fake_model.transcribe.call_args.args[0]
        self.assertTrue(str(transcribe_path).endswith('.webm'))
        self.assertNotEqual(Path(transcribe_path).name, 'voice.webm')

    def test_transcribe_audio_file_uses_download_root_for_cache_directory(self):
        audio_file = SimpleUploadedFile(
            'voice.webm',
            b'fake audio bytes',
            content_type='audio/webm',
        )
        fake_model = MagicMock()
        fake_model.transcribe.return_value = (
            [SimpleNamespace(text='患者は安静を保っている')],
            SimpleNamespace(language='ja'),
        )

        with tempfile.TemporaryDirectory() as tmpdir, override_settings(
            CLOSE_SIDE_WHISPER_MODEL_PATH=tmpdir,
            CLOSE_SIDE_WHISPER_MODEL_NAME='small',
        ), patch('close_side.transcription._load_whisper_model', return_value=fake_model) as mocked_load:
            from close_side.transcription import transcribe_audio_file

            result = transcribe_audio_file(audio_file, template_type='看護計画')

        self.assertEqual(result['text'], '患者は安静を保っている')
        self.assertEqual(result['model'], 'small')
        mocked_load.assert_called_once()
        self.assertEqual(mocked_load.call_args.args[0], 'small')
        self.assertEqual(mocked_load.call_args.kwargs['download_root'], tmpdir)

    def test_transcribe_audio_file_discovers_complete_snapshot_directory(self):
        audio_file = SimpleUploadedFile(
            'voice.webm',
            b'fake audio bytes',
            content_type='audio/webm',
        )
        fake_model = MagicMock()
        fake_model.transcribe.return_value = (
            [SimpleNamespace(text='患者は安静を保っている')],
            SimpleNamespace(language='ja'),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            snapshot = root / 'models--Systran--faster-whisper-small' / 'snapshots' / 'abc123'
            snapshot.mkdir(parents=True)
            for filename in ('config.json', 'model.bin', 'tokenizer.json', 'vocabulary.txt'):
                (snapshot / filename).write_text(filename, encoding='utf-8')

            with override_settings(CLOSE_SIDE_WHISPER_MODEL_PATH=tmpdir), patch(
                'close_side.transcription._load_whisper_model',
                return_value=fake_model,
            ) as mocked_load:
                from close_side.transcription import transcribe_audio_file

                result = transcribe_audio_file(audio_file, template_type='看護計画')

        self.assertEqual(result['text'], '患者は安静を保っている')
        self.assertEqual(result['model'], 'small')
        mocked_load.assert_called_once()
        self.assertEqual(mocked_load.call_args.args[0], str(snapshot))
        self.assertIsNone(mocked_load.call_args.kwargs['download_root'])

    def test_transcribe_audio_file_discovers_complete_model_directory_under_root(self):
        audio_file = SimpleUploadedFile(
            'voice.webm',
            b'fake audio bytes',
            content_type='audio/webm',
        )
        fake_model = MagicMock()
        fake_model.transcribe.return_value = (
            [SimpleNamespace(text='患者は安静を保っている')],
            SimpleNamespace(language='ja'),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            model_dir = root / 'faster-whisper-small'
            model_dir.mkdir(parents=True)
            for filename in ('config.json', 'model.bin', 'tokenizer.json', 'vocabulary.txt'):
                (model_dir / filename).write_text(filename, encoding='utf-8')

            with override_settings(CLOSE_SIDE_WHISPER_MODEL_PATH=tmpdir), patch(
                'close_side.transcription._load_whisper_model',
                return_value=fake_model,
            ) as mocked_load:
                from close_side.transcription import transcribe_audio_file

                result = transcribe_audio_file(audio_file, template_type='看護計画')

        self.assertEqual(result['text'], '患者は安静を保っている')
        self.assertEqual(result['model'], 'small')
        mocked_load.assert_called_once()
        self.assertEqual(mocked_load.call_args.args[0], str(model_dir))
        self.assertIsNone(mocked_load.call_args.kwargs['download_root'])

    def test_transcribe_audio_requires_audio_file(self):
        response = self.client.post(
            reverse('close_side:transcribe_audio'),
            data={
                'template_type': '看護計画',
                'transcript_source': 'manual_input',
            },
        )

        self.assertEqual(response.status_code, 400)
        payload = json.loads(response.content)
        self.assertEqual(payload['error'], '音声ファイルが必要です。')

    def test_sanitize_prompt_payload_for_dmz_removes_local_voice_fields(self):
        from close_side.views import _sanitize_prompt_payload_for_dmz

        payload = {
            'id': 'prompt_test',
            'metadata': {
                'input_mode': 'voice',
                'transcript_source': 'browser_recording',
                'source_input_data': {
                    'text': '患者は安静を保っている',
                    'audio_file_name': 'secret.wav',
                },
                'audio_file_name': 'secret.wav',
                'structured_input_labels': ['主訴'],
            },
            'content': {
                'text': '匿名化済み本文',
            },
        }

        sanitized = _sanitize_prompt_payload_for_dmz(payload)

        self.assertEqual(sanitized['metadata']['input_mode'], 'voice')
        self.assertNotIn('transcript_source', sanitized['metadata'])
        self.assertNotIn('source_input_data', sanitized['metadata'])
        self.assertNotIn('audio_file_name', sanitized['metadata'])
        self.assertEqual(sanitized['metadata']['structured_input_labels'], ['主訴'])
        self.assertEqual(sanitized['content']['text'], '匿名化済み本文')

    def test_prompt_send_to_dmz_sanitizes_prompt_json_before_write(self):
        source_id = 'prompt_voice_1234'
        prompt = Prompt.objects.create(
            source_id=source_id,
            name='看護計画 / prompt_voice_1234',
            content='匿名化済み本文',
            source_input_data={
                'template_type': '看護計画',
                'input_mode': 'voice',
                'text': '患者は安静を保っている',
                'transcript_source': 'browser_recording',
            },
            owner=self.user,
            status='draft',
        )
        RestoreMetadata.objects.create(
            source_id=source_id,
            template_type='看護計画',
            restore_map={'患者A': '山田太郎'},
            prompt_json={
                'prompt_text': '匿名化済み本文',
                'content': {'text': '匿名化済み本文'},
                'metadata': {
                    'input_mode': 'voice',
                    'transcript_source': 'browser_recording',
                    'source_input_data': {
                        'text': '患者は安静を保っている',
                        'audio_file_name': 'secret.wav',
                    },
                    'audio_file_name': 'secret.wav',
                },
            },
            owner=self.user,
            status='draft',
        )

        with tempfile.TemporaryDirectory() as tmpdir, patch(
            'close_side.views._close_to_open_dir',
            return_value=Path(tmpdir),
        ):
            response = self.client.post(reverse('close_side:prompt_send_to_dmz', args=[prompt.pk]))

            self.assertEqual(response.status_code, 302)
            exported_files = list(Path(tmpdir).glob('*.json'))
            self.assertEqual(len(exported_files), 1)
            payload = json.loads(exported_files[0].read_text(encoding='utf-8'))
            self.assertEqual(payload['metadata']['input_mode'], 'voice')
            self.assertNotIn('transcript_source', payload['metadata'])
            self.assertNotIn('source_input_data', payload['metadata'])
            self.assertNotIn('audio_file_name', payload['metadata'])
            self.assertEqual(payload['content']['text'], '匿名化済み本文')


@override_settings(ALLOWED_HOSTS=['testserver'], NETWORK_POLICY_ENFORCED=False)
class TemplateInputDefaultEditTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='close_user',
            password='pass12345',
        )
        self.client.force_login(self.user)

    def test_template_input_defaults_edit_updates_saved_defaults_and_home_preview(self):
        schema = get_template_input_schema('委員会議事録')
        post_data = {
            f'default__{field["key"]}': str(field.get('default') or '')
            for field in schema
        }
        post_data.update({
            f'required__{field["key"]}': ''
            for field in schema
        })
        post_data['default__overview'] = '会議名：\n開催日時：\n開催場所：\n参加者：\n出席状況：'
        post_data['required__overview'] = 'false'

        response = self.client.post(
            reverse('close_side:template_input_defaults_edit', args=['委員会議事録']),
            post_data,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            TemplateInputDefault.objects.get(template_type='委員会議事録', field_key='overview').default_text,
            '会議名：\n開催日時：\n開催場所：\n参加者：\n出席状況：',
        )
        self.assertFalse(
            TemplateInputDefault.objects.get(template_type='委員会議事録', field_key='overview').required_override
        )

        prompt = Prompt.objects.create(
            source_id='prompt_defaults_1234',
            name='委員会議事録 / prompt_defaults_1234',
            content='本文',
            source_input_data={
                'template_type': '委員会議事録',
                'input_mode': 'structured',
                'text': '',
                'structured_input': {},
            },
            owner=self.user,
            status='draft',
        )

        home_response = self.client.get(reverse('close_side:home'), {'reload_prompt_id': prompt.pk})

        self.assertEqual(home_response.status_code, 200)
        overview = next(field for field in home_response.context['structured_fields'] if field['key'] == 'overview')
        self.assertEqual(overview['value'], '会議名：\n開催日時：\n開催場所：\n参加者：\n出席状況：')
        self.assertFalse(overview['required'])


@override_settings(ALLOWED_HOSTS=['testserver'], NETWORK_POLICY_ENFORCED=False)
class TemplateInputFieldEditTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='close_user',
            password='pass12345',
        )
        self.client.force_login(self.user)

    def test_template_input_fields_edit_add_row_returns_re_rendered_page_without_saving(self):
        schema = get_template_input_schema('委員会議事録')
        post_data = {
            'deleted_field_keys': '',
            'editor_action': 'add_row',
        }
        for index, field in enumerate(schema):
            field_key = str(field['key'])
            post_data[f'field__{field_key}__field_key'] = field_key
            post_data[f'field__{field_key}__record_id'] = ''
            post_data[f'field__{field_key}__source_kind'] = 'builtin'
            post_data[f'field__{field_key}__label'] = str(field['label'])
            post_data[f'field__{field_key}__input_type'] = str(field.get('input_type') or 'textarea')
            post_data[f'field__{field_key}__section_title'] = str(field.get('section_title') or '')
            post_data[f'field__{field_key}__textarea_rows'] = str(field.get('textarea_rows') or 3)
            post_data[f'field__{field_key}__required'] = '1' if field.get('required') else '0'
            post_data[f'field__{field_key}__allow_other'] = '1' if field.get('allow_other') else '0'
            post_data[f'field__{field_key}__other_label'] = str(field.get('other_label') or 'その他')
            post_data[f'field__{field_key}__other_placeholder'] = str(field.get('other_placeholder') or '自由入力')
            post_data[f'field__{field_key}__help_text'] = str(field.get('help_text') or '')
            post_data[f'field__{field_key}__position'] = str((index + 1) * 10)

        response = self.client.post(
            reverse('close_side:template_input_fields_edit', args=['委員会議事録']),
            post_data,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('field_rows', response.context)
        self.assertEqual(response.context['newly_added_row_key'], 'new_0')
        self.assertEqual(len(response.context['field_rows']), len(schema) + 1)
        self.assertTrue(response.context['field_rows'][-1]['row_key'].startswith('new_'))
        self.assertEqual(response.context['field_rows'][-1]['source_kind'], 'new')
        self.assertEqual(response.context['field_rows'][-1]['label'], '')
        self.assertContains(response, 'is-newly-added')
        self.assertContains(response, 'autofocus')

    def test_template_input_fields_edit_updates_order_required_other_and_delete(self):
        schema = get_template_input_schema('委員会議事録')
        post_data = {
            'deleted_field_keys': 'decisions',
        }
        for index, field in enumerate(schema):
            field_key = str(field['key'])
            if field_key == 'decisions':
                continue
            post_data[f'field__{field_key}__field_key'] = field_key
            post_data[f'field__{field_key}__record_id'] = ''
            post_data[f'field__{field_key}__source_kind'] = 'builtin'
            post_data[f'field__{field_key}__label'] = '開催情報' if field_key == 'overview' else str(field['label'])
            post_data[f'field__{field_key}__input_type'] = 'textarea'
            post_data[f'field__{field_key}__section_title'] = '基本情報' if field_key == 'overview' else ''
            post_data[f'field__{field_key}__textarea_rows'] = '8' if field_key == 'overview' else '3'
            post_data[f'field__{field_key}__required'] = '1' if field_key == 'overview' else '0'
            post_data[f'field__{field_key}__allow_other'] = '0'
            post_data[f'field__{field_key}__other_label'] = 'その他'
            post_data[f'field__{field_key}__other_placeholder'] = '自由入力'
            post_data[f'field__{field_key}__help_text'] = ''
            post_data[f'field__{field_key}__position'] = str((index + 1) * 10)

        post_data.update({
            'field__new_0__field_key': '',
            'field__new_0__record_id': '',
            'field__new_0__source_kind': 'new',
            'field__new_0__label': '自由メモ',
            'field__new_0__input_type': 'checkbox_group',
            'field__new_0__section_title': '補足',
            'field__new_0__textarea_rows': '4',
            'field__new_0__required': '1',
            'field__new_0__allow_other': '1',
            'field__new_0__other_label': 'その他',
            'field__new_0__other_placeholder': '自由入力',
            'field__new_0__help_text': '',
            'field__new_0__position': '0',
        })

        response = self.client.post(
            reverse('close_side:template_input_fields_edit', args=['委員会議事録']),
            post_data,
        )

        self.assertEqual(response.status_code, 302)

        schema_after = get_template_input_schema('委員会議事録')
        custom_field = next(field for field in schema_after if field['label'] == '自由メモ')
        overview = next(field for field in schema_after if field['key'] == 'overview')

        self.assertEqual(custom_field['input_type'], 'checkbox_group')
        self.assertTrue(custom_field['required'])
        self.assertTrue(custom_field['allow_other'])
        self.assertEqual(custom_field['textarea_rows'], 4)
        self.assertEqual(overview['label'], '開催情報')
        self.assertEqual(overview['sort_order'], 10)
        self.assertEqual(overview['textarea_rows'], 8)
        self.assertNotIn('decisions', [field['key'] for field in schema_after])

        overview_row = TemplateInputField.objects.get(template_type='委員会議事録', field_key='overview')
        decisions_row = TemplateInputField.objects.get(template_type='委員会議事録', field_key='decisions')
        custom_row = TemplateInputField.objects.get(template_type='委員会議事録', field_key=custom_field['key'])

        self.assertTrue(overview_row.is_active)
        self.assertEqual(overview_row.label, '開催情報')
        self.assertEqual(overview_row.sort_order, 10)
        self.assertEqual(overview_row.textarea_rows, 8)
        self.assertFalse(decisions_row.is_active)
        self.assertTrue(custom_row.is_active)
        self.assertEqual(custom_row.input_type, 'checkbox_group')
        self.assertTrue(custom_row.allow_other)
        self.assertEqual(custom_row.textarea_rows, 4)

    def test_template_input_fields_edit_renders_reorder_and_toggle_controls(self):
        response = self.client.get(reverse('close_side:template_input_fields_edit', args=['委員会議事録']))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-add-field-row')
        self.assertContains(response, 'value="date"')
        self.assertContains(response, 'data-toggle-required')
        self.assertContains(response, 'data-toggle-other')
        self.assertContains(response, 'data-drag-handle')
        self.assertContains(response, '一番上')
        self.assertContains(response, 'その他')
        self.assertContains(response, 'data-role="field-textarea-rows"')
        self.assertContains(response, '大きさ（行数）')

    def test_home_renders_date_fields_with_calendar_input(self):
        response = self.client.post(
            reverse('close_side:home'),
            {
                'template': 'OT評価サマリー',
                'input_mode': 'structured',
            },
        )

        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertContains(response, 'type="date"')
        self.assertContains(response, 'data-input-type="date"')
        self.assertContains(response, 'class="field-area structured-field-input structured-date-input"')
        self.assertContains(response, '.structured-date-input {')
        self.assertContains(response, 'width: 12rem;')
        self.assertContains(response, 'justify-self: start;')
        self.assertLess(content.index('.field-area {'), content.index('.field-area.structured-date-input {'))
        evaluation_date = next(field for field in response.context['structured_fields'] if field['key'] == 'evaluation_date')
        self.assertEqual(evaluation_date['input_type'], 'date')

    def test_home_renders_checkbox_groups_without_main_textarea(self):
        response = self.client.post(
            reverse('close_side:home'),
            {
                'template': '入院時サマリー',
                'input_mode': 'structured',
            },
        )

        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        start = content.index('data-field-key="treatment_plan"')
        next_field = content.find('data-field-key="', start + 1)
        snippet = content[start: next_field if next_field != -1 else len(content)]
        self.assertIn('type="checkbox"', snippet)
        self.assertIn('data-structured-other-input="true"', snippet)
        self.assertNotIn('data-structured-text-input="true"', snippet)


@override_settings(ALLOWED_HOSTS=['testserver'], NETWORK_POLICY_ENFORCED=False)
class TemplateCheckboxOptionsEditTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='close_user',
            password='pass12345',
        )
        self.client.force_login(self.user)

    def test_template_checkbox_options_edit_adds_updates_and_deletes_options(self):
        group = TemplateInputCheckboxGroup.objects.get(
            template_type='入院時サマリー',
            field_key='treatment_plan',
        )
        group.options.all().delete()
        existing_option = TemplateInputCheckboxOption.objects.create(
            group=group,
            text='安静',
            sort_order=0,
        )
        TemplateInputCheckboxOption.objects.create(
            group=group,
            text='輸液',
            sort_order=10,
        )

        response = self.client.post(
            reverse('close_side:template_checkbox_options_edit', args=['入院時サマリー']),
            {
                f'checkbox__treatment_plan__opt_{existing_option.pk}__id': str(existing_option.pk),
                f'checkbox__treatment_plan__opt_{existing_option.pk}__text': '安静(更新)',
                f'checkbox__treatment_plan__opt_{existing_option.pk}__position': '0',
                'checkbox__treatment_plan__new_0__id': '',
                'checkbox__treatment_plan__new_0__text': '薬剤調整',
                'checkbox__treatment_plan__new_0__position': '10',
            },
        )

        self.assertEqual(response.status_code, 302)
        options = list(TemplateInputCheckboxOption.objects.filter(group=group).order_by('sort_order', 'id'))
        self.assertEqual([option.text for option in options], ['安静(更新)', '薬剤調整'])

        schema = get_template_input_schema('入院時サマリー')
        treatment_plan = next(field for field in schema if field['key'] == 'treatment_plan')
        self.assertEqual(
            [option['value'] for option in treatment_plan.get('options') or []],
            ['安静(更新)', '薬剤調整'],
        )

    def test_template_checkbox_options_edit_reorders_options_by_position(self):
        group = TemplateInputCheckboxGroup.objects.get(
            template_type='入院時サマリー',
            field_key='treatment_plan',
        )
        group.options.all().delete()
        first_option = TemplateInputCheckboxOption.objects.create(
            group=group,
            text='安静',
            sort_order=0,
        )
        second_option = TemplateInputCheckboxOption.objects.create(
            group=group,
            text='輸液',
            sort_order=10,
        )
        third_option = TemplateInputCheckboxOption.objects.create(
            group=group,
            text='薬剤調整',
            sort_order=20,
        )

        response = self.client.post(
            reverse('close_side:template_checkbox_options_edit', args=['入院時サマリー']),
            {
                f'checkbox__treatment_plan__opt_{first_option.pk}__id': str(first_option.pk),
                f'checkbox__treatment_plan__opt_{first_option.pk}__text': '安静',
                f'checkbox__treatment_plan__opt_{first_option.pk}__position': '20',
                f'checkbox__treatment_plan__opt_{second_option.pk}__id': str(second_option.pk),
                f'checkbox__treatment_plan__opt_{second_option.pk}__text': '輸液',
                f'checkbox__treatment_plan__opt_{second_option.pk}__position': '0',
                f'checkbox__treatment_plan__opt_{third_option.pk}__id': str(third_option.pk),
                f'checkbox__treatment_plan__opt_{third_option.pk}__text': '薬剤調整',
                f'checkbox__treatment_plan__opt_{third_option.pk}__position': '10',
            },
        )

        self.assertEqual(response.status_code, 302)
        options = list(TemplateInputCheckboxOption.objects.filter(group=group).order_by('sort_order', 'id'))
        self.assertEqual([option.text for option in options], ['輸液', '薬剤調整', '安静'])

    def test_template_checkbox_options_edit_supports_text_fields(self):
        response = self.client.post(
            reverse('close_side:template_checkbox_options_edit', args=['委員会議事録']),
            {
                'checkbox__agenda__new_0__id': '',
                'checkbox__agenda__new_0__text': '検討事項',
                'checkbox__agenda__new_0__position': '0',
            },
        )

        self.assertEqual(response.status_code, 302)

        schema = get_template_input_schema('委員会議事録')
        agenda = next(field for field in schema if field['key'] == 'agenda')
        self.assertEqual(
            [option['value'] for option in agenda.get('options') or []],
            ['検討事項'],
        )

    def test_template_checkbox_options_edit_renders_reorder_controls(self):
        response = self.client.get(reverse('close_side:template_checkbox_options_edit', args=['入院時サマリー']))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn('data-add-option-row', content)
        self.assertIn('data-drag-handle', content)
        self.assertIn('data-move-row="top"', content)
        self.assertIn('data-move-row="bottom"', content)
        self.assertIn('const nextPosition = Number(', content)
        self.assertIn('is-newly-added', content)


@override_settings(ALLOWED_HOSTS=['testserver'], NETWORK_POLICY_ENFORCED=False)
class RestoredResultEditTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='close_user',
            password='pass12345',
        )
        self.client.force_login(self.user)

    def test_result_rerestore_updates_restore_map_and_result_text(self):
        source_id = 'prompt_restore_edit_1234'
        metadata = RestoreMetadata.objects.create(
            source_id=source_id,
            template_type='委員会議事録',
            restore_map={
                '患者A': '山田太郎',
                '看護師A': '佐藤看護師',
            },
            prompt_json={'metadata': {'input_mode': 'free'}},
            owner=self.user,
            status='imported_to_close',
        )
        result = RestoredResult.objects.create(
            source_id=source_id,
            result_id='result_1234',
            template_type='委員会議事録',
            result_text='患者Aと看護師Aが対応した。',
            restored_text='山田太郎と佐藤看護師が対応した。',
            result_json={
                'id': 'result_1234',
                'source_id': source_id,
                'result_text': '患者Aと看護師Aが対応した。',
                'metadata': {'reviewer': 'unknown'},
            },
            imported_filename='result.json',
            reviewer='unknown',
            owner=self.user,
            status='imported',
        )

        response = self.client.post(
            reverse('close_side:result_rerestore', args=[result.pk]),
            {
                'restore_rows_json': json.dumps([
                    {'old_label': '患者A', 'label': '患者B', 'original': '山田太郎'},
                    {'old_label': '', 'label': '家族A', 'original': '田中花子'},
                ], ensure_ascii=False),
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)

        metadata.refresh_from_db()
        result.refresh_from_db()
        self.assertEqual(metadata.restore_map, {
            '患者B': '山田太郎',
            '家族A': '田中花子',
        })
        self.assertEqual(result.result_text, '患者Bと看護師Aが対応した。')
        self.assertEqual(result.restored_text, '山田太郎と看護師Aが対応した。')
        self.assertContains(response, '匿名ラベル追加')
        self.assertContains(response, '再復元する')
        self.assertContains(response, '患者B')
        self.assertContains(response, '家族A')

    def test_result_detail_and_preview_show_patient_label_next_to_id(self):
        source_id = 'prompt_restore_label_1234'
        Prompt.objects.create(
            source_id=source_id,
            name='看護計画 / prompt_restore_label_1234',
            content='匿名化済み本文',
            source_input_data={
                'template_type': '看護計画',
                'input_mode': 'free',
                'text': '山田太郎は本日退院した。',
                'patient_id': 'P001',
                'patient': {
                    'patient_id': 'P001',
                    'anonymized_patient_id': '9900P001',
                    'full_name': '山田太郎',
                    'birth_date': '1980-01-02',
                    'sex': 'male',
                    'primary_diagnosis': '統合失調症',
                },
            },
            owner=self.user,
            status='draft',
        )
        RestoreMetadata.objects.create(
            source_id=source_id,
            template_type='看護計画',
            restore_map={'患者A': '山田太郎'},
            prompt_json={'metadata': {'input_mode': 'free'}},
            owner=self.user,
            status='imported_to_close',
        )
        result = RestoredResult.objects.create(
            source_id=source_id,
            result_id='result_1234',
            template_type='看護計画',
            result_text='患者Aは本日退院した。',
            restored_text='山田太郎は本日退院した。',
            result_json={
                'id': 'result_1234',
                'source_id': source_id,
                'result_text': '患者Aは本日退院した。',
                'metadata': {'reviewer': 'unknown'},
            },
            imported_filename='result.json',
            reviewer='unknown',
            owner=self.user,
            status='imported',
        )

        detail_response = self.client.get(reverse('close_side:result_detail', args=[result.pk]))
        preview_response = self.client.get(reverse('close_side:result_history_preview', args=[result.pk]))

        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(preview_response.status_code, 200)
        self.assertContains(detail_response, '患者ID / 氏名')
        self.assertContains(detail_response, '9900P001 山田太郎')
        self.assertContains(preview_response, '患者ID / 氏名')
        self.assertContains(preview_response, '9900P001 山田太郎')


@override_settings(ALLOWED_HOSTS=['testserver'], NETWORK_POLICY_ENFORCED=False)
class PatientManagementTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='close_user',
            password='pass12345',
        )
        self.client.force_login(self.user)

    def test_patient_crud_and_lookup(self):
        create_response = self.client.post(
            reverse('close_side:patient_create'),
            {
                'patient_id': 'P001',
                'surname': '山田',
                'given_name': '太郎',
                'kana_surname': 'やまだ',
                'kana_given_name': 'たろう',
                'birth_date': '1980-01-02',
                'sex': 'male',
                'primary_diagnosis': '統合失調症',
            },
        )

        self.assertEqual(create_response.status_code, 302)
        patient = Patient.objects.get(patient_id='P001')
        self.assertEqual(patient.full_name, '山田太郎')

        lookup_response = self.client.get(reverse('close_side:patient_lookup', args=['P001']))
        self.assertEqual(lookup_response.status_code, 200)
        lookup_payload = json.loads(lookup_response.content)
        self.assertTrue(lookup_payload['found'])
        self.assertEqual(lookup_payload['patient']['full_name'], '山田太郎')
        self.assertEqual(lookup_payload['patient']['anonymized_patient_id'], '9900P001')
        self.assertEqual(lookup_payload['patient']['birth_date_display'], '1980-01-02')
        self.assertEqual(lookup_payload['patient']['sex_display'], '男')
        self.assertEqual(lookup_payload['patient']['primary_diagnosis'], '統合失調症')

        edit_response = self.client.post(
            reverse('close_side:patient_edit', args=[patient.pk]),
            {
                'patient_id': 'P001',
                'surname': '山田',
                'given_name': '次郎',
                'kana_surname': 'やまだ',
                'kana_given_name': 'じろう',
                'birth_date': '1980-01-02',
                'sex': 'female',
                'primary_diagnosis': '統合失調症',
            },
        )

        self.assertEqual(edit_response.status_code, 302)
        patient.refresh_from_db()
        self.assertEqual(patient.full_name, '山田次郎')
        self.assertEqual(patient.sex, 'female')

        delete_response = self.client.post(reverse('close_side:patient_delete', args=[patient.pk]))
        self.assertEqual(delete_response.status_code, 302)
        self.assertFalse(Patient.objects.filter(patient_id='P001').exists())

    def test_patient_list_search_and_sort(self):
        Patient.objects.create(
            patient_id='P100',
            surname='中村',
            given_name='太郎',
            kana_surname='なかむら',
            kana_given_name='たろう',
            birth_date=date(1992, 1, 1),
            sex='other',
            primary_diagnosis='統合失調症',
        )
        Patient.objects.create(
            patient_id='P200',
            surname='青木',
            given_name='花子',
            kana_surname='あおき',
            kana_given_name='はなこ',
            birth_date=date(1985, 1, 1),
            sex='male',
            primary_diagnosis='うつ病',
        )
        Patient.objects.create(
            patient_id='P300',
            surname='佐藤',
            given_name='次郎',
            kana_surname='さとう',
            kana_given_name='じろう',
            birth_date=date(1995, 1, 1),
            sex='female',
            primary_diagnosis='統合失調症',
        )

        search_response = self.client.get(
            reverse('close_side:patient_list'),
            {
                'patient_id': 'P3',
                'kana': 'さと',
                'sex': 'female',
                'birth_date': '1995-01-01',
                'primary_diagnosis': '統合',
                'sort': 'patient_id',
            },
        )

        self.assertEqual(search_response.status_code, 200)
        self.assertEqual([patient.patient_id for patient in search_response.context['patients']], ['P300'])

        by_id_response = self.client.get(reverse('close_side:patient_list'), {'sort': 'patient_id'})
        by_kana_response = self.client.get(reverse('close_side:patient_list'), {'sort': 'kana'})
        by_sex_response = self.client.get(reverse('close_side:patient_list'), {'sort': 'sex'})
        by_birth_response = self.client.get(reverse('close_side:patient_list'), {'sort': 'birth_date'})

        self.assertEqual([patient.patient_id for patient in by_id_response.context['patients']], ['P100', 'P200', 'P300'])
        self.assertEqual([patient.patient_id for patient in by_kana_response.context['patients']], ['P200', 'P300', 'P100'])
        self.assertEqual([patient.patient_id for patient in by_sex_response.context['patients']], ['P200', 'P300', 'P100'])
        self.assertEqual([patient.patient_id for patient in by_birth_response.context['patients']], ['P200', 'P100', 'P300'])

    def test_patient_csv_import_updates_existing_rows_without_overwriting_blank_values(self):
        Patient.objects.create(
            patient_id='P001',
            surname='山田',
            given_name='太郎',
            kana_surname='やまだ',
            kana_given_name='たろう',
            birth_date=date(1980, 1, 2),
            sex='male',
            primary_diagnosis='旧病名',
        )

        csv_text = (
            'ID,姓,名,ふりかな姓,ふりかな名,生年月日,性別,主病名\n'
            'P001,山田,次郎,やまだ,, ,女,\n'
            'P002,佐藤,花子,さとう,はなこ,1990-02-03,女,新病名\n'
        )
        upload = SimpleUploadedFile('patients.csv', csv_text.encode('utf-8'), content_type='text/csv')

        response = self.client.post(
            reverse('close_side:patient_import'),
            {'csv_file': upload},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        existing = Patient.objects.get(patient_id='P001')
        imported = Patient.objects.get(patient_id='P002')
        self.assertEqual(existing.given_name, '次郎')
        self.assertEqual(existing.kana_surname, 'やまだ')
        self.assertEqual(existing.kana_given_name, 'たろう')
        self.assertEqual(existing.birth_date, date(1980, 1, 2))
        self.assertEqual(existing.sex, 'female')
        self.assertEqual(existing.primary_diagnosis, '旧病名')
        self.assertEqual(imported.full_name, '佐藤花子')
        self.assertEqual(imported.sex, 'female')
        self.assertEqual(imported.birth_date, date(1990, 2, 3))

    def test_patient_csv_import_rejects_csv_without_patient_ids(self):
        csv_text = (
            '氏名,生年月日\n'
            'テスト,1990/1/1\n'
        )
        upload = SimpleUploadedFile('patients.csv', csv_text.encode('utf-8'), content_type='text/csv')

        response = self.client.post(
            reverse('close_side:patient_import'),
            {'csv_file': upload},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '有効な患者IDが見つかりませんでした。')
        self.assertEqual(Patient.objects.count(), 0)

    def test_home_uses_patient_master_and_forces_patient_label_for_non_committee_templates(self):
        Patient.objects.create(
            patient_id='P001',
            surname='山田',
            given_name='太郎',
            kana_surname='やまだ',
            kana_given_name='たろう',
            birth_date=date(1980, 1, 2),
            sex='male',
            primary_diagnosis='統合失調症',
        )

        response = self.client.post(
            reverse('close_side:home'),
            {
                'template': '看護計画',
                'input_mode': 'free',
                'text': '山田太郎は本日退院した。',
                'patient_id': 'P001',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['show_patient_panel'])
        self.assertEqual(response.context['patient_profile']['full_name'], '山田太郎')
        self.assertEqual(response.context['patient_profile']['anonymized_patient_id'], '9900P001')
        self.assertEqual(response.context['patient_profile']['birth_date_display'], '1980-01-02')
        self.assertEqual(response.context['patient_profile']['sex_display'], '男')
        self.assertEqual(response.context['patient_profile']['primary_diagnosis'], '統合失調症')
        self.assertIn('患者本人A', response.context['text_items'][0]['anonymized'])
        self.assertNotIn('山田太郎', response.context['text_items'][0]['anonymized'])
        self.assertEqual(response.context['restore_map']['患者本人A'], '山田太郎')

        source_id = response.context['source_id']
        prompt = Prompt.objects.get(source_id=source_id)
        self.assertEqual(prompt.source_input_data['patient_id'], 'P001')
        self.assertEqual(prompt.source_input_data['patient']['patient_id'], 'P001')
        self.assertEqual(prompt.source_input_data['patient']['anonymized_patient_id'], '9900P001')

    def test_home_hides_patient_panel_for_committee_template(self):
        response = self.client.post(
            reverse('close_side:home'),
            {
                'template': '委員会議事録',
                'input_mode': 'free',
                'text': '会議を行った。',
                'patient_id': 'P001',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['show_patient_panel'])
        self.assertNotContains(response, '患者マスタ連携')
