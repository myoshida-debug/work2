import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('anonymizer_app', '0007_template_source_filename'),
    ]

    operations = [
        migrations.CreateModel(
            name='RestoredResult',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source_id', models.CharField(db_index=True, max_length=255)),
                ('result_id', models.CharField(blank=True, default='', max_length=255)),
                ('template_type', models.CharField(blank=True, default='', max_length=255)),
                ('result_text', models.TextField()),
                ('restored_text', models.TextField()),
                ('result_json', models.JSONField(blank=True, null=True)),
                ('imported_filename', models.CharField(blank=True, default='', max_length=255)),
                ('reviewer', models.CharField(blank=True, default='', max_length=255)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
