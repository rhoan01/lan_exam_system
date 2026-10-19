from django.db import migrations, models


def unpublish_unassigned_exams(apps, schema_editor):
    Exam = apps.get_model('exams', 'Exam')
    # Existing exams predate program scoping. Fail closed rather than guessing
    # their intended program and accidentally exposing an assessment.
    Exam.objects.filter(is_published=True).update(is_published=False)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_program_studentprofile_program'),
        ('exams', '0008_question_image_alter_question_question_type_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='exam',
            name='access_code',
            field=models.CharField(
                blank=True,
                help_text='Auto-generated when the exam is published. Lets an irregular student outside the target program, year, or section unlock this exam.',
                max_length=8,
                null=True,
                unique=True,
            ),
        ),
        migrations.AddField(
            model_name='exam',
            name='available_to_all_programs',
            field=models.BooleanField(
                default=False,
                help_text='Explicitly make this exam available to every academic program.',
            ),
        ),
        migrations.AddField(
            model_name='exam',
            name='target_programs',
            field=models.ManyToManyField(
                blank=True,
                help_text='Only students in these programs can see or take this exam.',
                related_name='exams',
                to='accounts.program',
            ),
        ),
        migrations.RunPython(unpublish_unassigned_exams, migrations.RunPython.noop),
    ]
