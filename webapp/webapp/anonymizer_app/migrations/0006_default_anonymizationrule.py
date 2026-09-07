from django.db import migrations


def create_default_rule(apps, schema_editor):
    AnonymizationRule = apps.get_model('anonymizer_app', 'AnonymizationRule')
    if not AnonymizationRule.objects.filter(name='default').exists():
        AnonymizationRule.objects.create(
            name='default',
            content='氏名、住所、電話番号、メールアドレス、ID、日付などの個人情報を匿名化します。ここに追加の匿名化ルールを記述してください。',
        )


def reverse_default_rule(apps, schema_editor):
    AnonymizationRule = apps.get_model('anonymizer_app', 'AnonymizationRule')
    AnonymizationRule.objects.filter(name='default').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('anonymizer_app', '0005_anonymizationrule'),
    ]

    operations = [
        migrations.RunPython(create_default_rule, reverse_default_rule),
    ]
