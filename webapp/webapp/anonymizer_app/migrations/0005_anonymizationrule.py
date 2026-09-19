from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('anonymizer_app', '0004_template_basic_additional'),
    ]

    operations = [
        migrations.CreateModel(
            name='AnonymizationRule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(default='default', max_length=255)),
                ('content', models.TextField()),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
