from django.db import migrations, models


def reset_legacy_access_codes(apps, schema_editor):
    Exam = apps.get_model('exams', 'Exam')
    # The previous eight-character codes bypassed class targeting. They must
    # never become valid under the new five-character exam gate.
    Exam.objects.update(access_code=None)


class Migration(migrations.Migration):

    dependencies = [
        ('exams', '0009_exam_program_access'),
    ]

    operations = [
        migrations.RunPython(reset_legacy_access_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='exam',
            name='access_code',
            field=models.CharField(
                blank=True,
                help_text='Five-character code required before an eligible student can open this exam.',
                max_length=5,
                null=True,
                unique=True,
            ),
        ),
        migrations.AddField(
            model_name='exam',
            name='access_code_enabled',
            field=models.BooleanField(
                default=False,
                help_text='Students cannot open this exam unless code access is enabled.',
            ),
        ),
    ]
