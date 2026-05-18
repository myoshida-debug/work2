from pathlib import Path

from django.core.management.base import BaseCommand

from anonymizer_app.models import Template


TEMPLATE_SPECS = [
    {
        'filename': 'admission.txt',
        'template_type': '入院時サマリー',
        'name': '入院時サマリー（詳細版）',
    },
    {
        'filename': 'discharge.txt',
        'template_type': '退院時サマリー',
        'name': '退院時サマリー',
    },
    {
        'filename': 'midterm.txt',
        'template_type': '中間サマリー',
        'name': '中間サマリー',
    },
    {
        'filename': 'incident.txt',
        'template_type': 'インシデントレポート',
        'name': 'インシデントレポート（様式1-3）',
    },
    {
        'filename': 'incident2.txt',
        'template_type': 'インシデントレポート',
        'name': 'インシデントレポート（簡易版）',
    },
    {
        'filename': 'committee.txt',
        'template_type': '委員会議事録',
        'name': '委員会議事録',
    },
    {
        'filename': 'nursing.txt',
        'template_type': '看護計画',
        'name': '看護計画',
    },
]


def split_common_base(default_text: str) -> str:
    marker = 'あなたは医療文書作成支援AIです。'
    first = default_text.find(marker)
    if first == -1:
        return default_text.strip()

    second = default_text.find(marker, first + len(marker))
    if second == -1:
        return default_text.strip()
    return default_text[:second].strip()


def extract_additional_content(full_text: str, common_base: str) -> str:
    normalized = full_text.strip()
    if normalized.startswith(common_base):
        return normalized[len(common_base):].strip()
    return normalized


class Command(BaseCommand):
    help = 'Load prompt templates from anonymizer_app/prompt_templates into Template records.'

    def handle(self, *args, **options):
        template_dir = Path(__file__).resolve().parents[2] / 'prompt_templates'
        default_text = (template_dir / 'default.txt').read_text(encoding='utf-8')
        basic_content = split_common_base(default_text)

        created_count = 0
        updated_count = 0

        for spec in TEMPLATE_SPECS:
            path = template_dir / spec['filename']
            if not path.exists():
                self.stderr.write(self.style.WARNING(f'Skipped missing template file: {path}'))
                continue

            full_text = path.read_text(encoding='utf-8').strip()
            additional_content = extract_additional_content(full_text, basic_content)
            content = f'{basic_content}\n\n{additional_content}' if additional_content else basic_content

            _, created = Template.objects.update_or_create(
                name=spec['name'],
                defaults={
                    'template_type': spec['template_type'],
                    'content': content,
                    'basic_content': basic_content,
                    'additional_content': additional_content,
                },
            )

            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'Created: {spec["name"]}'))
            else:
                updated_count += 1
                self.stdout.write(f'Updated: {spec["name"]}')

        self.stdout.write(self.style.SUCCESS(
            f'Prompt template load complete. created={created_count}, updated={updated_count}'
        ))

