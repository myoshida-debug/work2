from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(ALLOWED_HOSTS=['testserver'], NETWORK_POLICY_ENFORCED=False)
class OpenSideResultExportTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='open_admin',
            password='pass12345',
        )
        self.client.force_login(self.user)

    def test_create_result_prepends_anonymized_patient_id_to_output_json(self):
        filename = 'prompt_test.json'
        prompt_payload = {
            'id': 'prompt_test',
            'source_id': 'prompt_test',
            'template_type': '看護計画',
            'prompt_text': (
                '【患者基本情報】\n'
                '・匿名ID: 9900P001\n'
                '・氏名: 山田太郎\n'
                '・性別: 男\n'
                '・生年月日: 1980-01-02\n'
                '・主病名: 統合失調症\n'
            ),
            'metadata': {
                'source_id': 'prompt_test',
                'owner_user_id': self.user.id,
                'owner_username': self.user.get_username(),
                'template_type': '看護計画',
                'input_mode': 'free',
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            logs_dir = tmp_path / 'logs'
            output_dir = tmp_path / 'open_to_close'
            logs_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)
            (logs_dir / filename).write_text(json.dumps(prompt_payload, ensure_ascii=False, indent=2), encoding='utf-8')

            with patch('open_side.views._logs_dir', return_value=logs_dir), patch(
                'open_side.views._open_to_close_dir',
                return_value=output_dir,
            ):
                response = self.client.post(
                    reverse('open_side:create_result', args=[filename]),
                    {
                        'result_text': '患者は安静を保っている。',
                        'reviewer': 'AI',
                    },
                )

            self.assertEqual(response.status_code, 200)
            output_filename = response.context['output_filename']
            output_path = output_dir / output_filename
            raw_output = output_path.read_text(encoding='utf-8')
            payload = json.loads(raw_output)

            self.assertTrue(raw_output.startswith('{\n  "anonymized_patient_id": "9900P001"'))
            self.assertEqual(list(payload.keys())[0], 'anonymized_patient_id')
            self.assertEqual(payload['anonymized_patient_id'], '9900P001')
            self.assertEqual(payload['source_id'], 'prompt_test')
            self.assertEqual(payload['result_text'], '患者は安静を保っている。')


@override_settings(ALLOWED_HOSTS=['testserver'], NETWORK_POLICY_ENFORCED=False,
                   OPENAI_API_KEY='test-key', OPENAI_OPEN_MODEL='gpt-4.1-mini')
class OpenSideGenerationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='generator')
        self.client.force_login(self.user)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'prompt.json'
        self.path.write_text(json.dumps({'id': 'source-1', 'prompt_text': '元の文章',
                                        'metadata': {'owner_user_id': self.user.pk}}))
        patcher = patch('open_side.views._logs_dir', return_value=self.path.parent)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.url = reverse('open_side:generate_answer', args=['prompt.json'])

    @patch('openai.OpenAI')
    def test_generates_from_edited_prompt(self, client):
        response = client.return_value.__enter__.return_value.responses.create.return_value
        response.output_text = '生成された回答'
        response.status = 'completed'
        result = self.client.post(self.url, {'prompt': '編集した文章'})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['answer'], '生成された回答')
        client.return_value.__enter__.return_value.responses.create.assert_called_once_with(
            model='gpt-4.1-mini', input='編集した文章', max_output_tokens=4096, store=False)

    @patch('openai.OpenAI')
    def test_rejects_other_owner_and_invalid_input(self, client):
        for prompt, code in [('  ', 400), ('a' * 30001, 413)]:
            self.assertEqual(self.client.post(self.url, {'prompt': prompt}).status_code, code)
        self.path.write_text(json.dumps({'metadata': {'owner_user_id': self.user.pk + 1}}))
        self.assertEqual(self.client.post(self.url, {'prompt': 'test'}).status_code, 403)
        client.assert_not_called()

    @patch('openai.OpenAI')
    def test_configuration_and_api_errors(self, client):
        with self.settings(OPENAI_API_KEY=''):
            self.assertEqual(self.client.post(self.url, {'prompt': 'test'}).status_code, 503)
        client.side_effect = RuntimeError('secret provider details')
        result = self.client.post(self.url, {'prompt': 'test'})
        self.assertEqual(result.status_code, 502)
        self.assertNotContains(result, 'secret provider details', status_code=502)

    @patch('openai.OpenAI')
    def test_incomplete_answer_is_not_returned(self, client):
        response = client.return_value.__enter__.return_value.responses.create.return_value
        response.output_text = '途中の回答'
        response.status = 'incomplete'
        self.assertEqual(self.client.post(self.url, {'prompt': 'test'}).status_code, 502)

    def test_page_and_endpoint_protection(self):
        page = self.client.get(reverse('open_side:imported_prompt', args=['prompt.json']))
        self.assertContains(page, 'プロンプト入力')
        self.assertContains(page, 'id_result_text')
        self.assertNotContains(page, 'chatgpt.com')
        self.assertEqual(self.client.get(self.url).status_code, 405)
        from django.test import Client
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(csrf_client.post(self.url, {'prompt': 'test'}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(self.url, {'prompt': 'test'}).status_code, 302)
