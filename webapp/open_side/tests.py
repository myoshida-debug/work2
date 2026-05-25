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
