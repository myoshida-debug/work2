from django.db import migrations, models


def backfill_admin_only_patients(apps, schema_editor):
    Patient = apps.get_model('anonymizer_app', 'Patient')
    Staff = apps.get_model('anonymizer_app', 'Staff')

    staff_keys = set(
        Staff.objects.values_list('surname', 'given_name', 'kana_surname', 'kana_given_name')
    )
    if not staff_keys:
        return

    patients_to_update = []
    for patient in Patient.objects.all().only(
        'pk',
        'surname',
        'given_name',
        'kana_surname',
        'kana_given_name',
        'is_admin_only',
    ):
        key = (
            patient.surname or '',
            patient.given_name or '',
            patient.kana_surname or '',
            patient.kana_given_name or '',
        )
        if key in staff_keys and not patient.is_admin_only:
            patient.is_admin_only = True
            patients_to_update.append(patient)

    if patients_to_update:
        Patient.objects.bulk_update(patients_to_update, ['is_admin_only'])


class Migration(migrations.Migration):
    dependencies = [
        ('anonymizer_app', '0027_patient_linked_person_code'),
    ]

    operations = [
        migrations.AddField(
            model_name='patient',
            name='is_admin_only',
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.RunPython(backfill_admin_only_patients, migrations.RunPython.noop),
    ]
