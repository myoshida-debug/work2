from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('anonymizer_app', '0006_default_anonymizationrule'),
    ]

    operations = [
        migrations.AddField(
            model_name='template',
            name='source_filename',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
    ]
