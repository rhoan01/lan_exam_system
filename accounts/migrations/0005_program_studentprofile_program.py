import re

import django.db.models.deletion
from django.db import migrations, models


def migrate_courses_to_programs(apps, schema_editor):
    Program = apps.get_model('accounts', 'Program')
    StudentProfile = apps.get_model('accounts', 'StudentProfile')
    programs_by_name = {}

    for profile in StudentProfile.objects.all().iterator():
        name = (profile.course or '').strip() or 'Unassigned'
        lookup_key = name.casefold()
        program = programs_by_name.get(lookup_key)
        if program is None:
            base_code = re.sub(r'[^A-Z0-9]+', '-', name.upper()).strip('-')[:30]
            base_code = base_code or 'UNASSIGNED'
            code = base_code
            suffix = 2
            while Program.objects.filter(code=code).exists():
                existing = Program.objects.filter(code=code).first()
                if existing.name.casefold() == lookup_key:
                    program = existing
                    break
                suffix_text = f'-{suffix}'
                code = f'{base_code[:30 - len(suffix_text)]}{suffix_text}'
                suffix += 1
            if program is None:
                program = Program.objects.create(code=code, name=name)
            programs_by_name[lookup_key] = program

        profile.program_id = program.pk
        profile.save(update_fields=['program'])


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_move_student_name_to_user'),
    ]

    operations = [
        migrations.CreateModel(
            name='Program',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=30, unique=True)),
                ('name', models.CharField(max_length=150)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={'ordering': ['code']},
        ),
        migrations.AlterField(
            model_name='studentprofile',
            name='course',
            field=models.CharField(editable=False, max_length=100),
        ),
        migrations.AddField(
            model_name='studentprofile',
            name='program',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='students',
                to='accounts.program',
            ),
        ),
        migrations.RunPython(migrate_courses_to_programs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='studentprofile',
            name='program',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='students',
                to='accounts.program',
            ),
        ),
    ]
