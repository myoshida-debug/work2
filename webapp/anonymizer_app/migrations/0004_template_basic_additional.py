# Generated manually to add basic_content and additional_content to Template

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('anonymizer_app', '0003_template'),
    ]

    operations = [
        migrations.AddField(
            model_name='template',
            name='basic_content',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='template',
            name='additional_content',
            field=models.TextField(blank=True, default=''),
        ),
    ]
