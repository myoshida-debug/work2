from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from anonymizer_app.models import Prompt, RestoreMetadata


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
