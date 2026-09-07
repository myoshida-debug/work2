from django.db import migrations


def seed_models(apps, schema_editor):
    ModelSetting = apps.get_model('internal_ai', 'ModelSetting')
    ModelSetting.objects.get_or_create(
        model_code='gpt-4o-mini',
        defaults={
            'display_name': '標準AI',
            'permission_level': 1,
            # 初期値。実際の契約単価に合わせて管理画面で必ず更新する。
            'input_price_per_million': '0.150000',
            'output_price_per_million': '0.600000',
            'enabled': True,
        },
    )
    ModelSetting.objects.get_or_create(
        model_code='gpt-4o',
        defaults={
            'display_name': '高性能AI',
            'permission_level': 2,
            'input_price_per_million': '2.500000',
            'output_price_per_million': '10.000000',
            'enabled': True,
        },
    )


def remove_seed_models(apps, schema_editor):
    ModelSetting = apps.get_model('internal_ai', 'ModelSetting')
    ModelSetting.objects.filter(model_code__in=['gpt-4o-mini', 'gpt-4o']).delete()


class Migration(migrations.Migration):
    dependencies = [('internal_ai', '0002_department_notification_systemsetting_securityevent_and_more')]
    operations = [migrations.RunPython(seed_models, remove_seed_models)]
