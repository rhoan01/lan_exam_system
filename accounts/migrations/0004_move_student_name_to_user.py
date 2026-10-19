from django.db import migrations, models


def move_student_names_to_user(apps, schema_editor):
    StudentProfile = apps.get_model('accounts', 'StudentProfile')

    for profile in StudentProfile.objects.select_related('user').iterator():
        user = profile.user
        full_name = profile.full_name.strip()

        # Registrations already copied the name to User. This fallback keeps
        # profiles created through older admin/import workflows from losing it.
        if not full_name:
            continue

        changed_fields = []
        if not user.first_name and not user.last_name:
            name_parts = full_name.rsplit(maxsplit=1)
            user.first_name = name_parts[0]
            user.last_name = name_parts[1] if len(name_parts) > 1 else ''
            changed_fields = ['first_name', 'last_name']
        elif user.first_name and not user.last_name:
            if full_name.casefold().startswith(user.first_name.casefold() + ' '):
                remaining_name = full_name[len(user.first_name):].strip()
            else:
                name_parts = full_name.rsplit(maxsplit=1)
                remaining_name = name_parts[1] if len(name_parts) > 1 else ''
            if remaining_name:
                user.last_name = remaining_name
                changed_fields = ['last_name']
        elif user.last_name and not user.first_name:
            if full_name.casefold().endswith(' ' + user.last_name.casefold()):
                remaining_name = full_name[:-len(user.last_name)].strip()
            else:
                name_parts = full_name.rsplit(maxsplit=1)
                remaining_name = name_parts[0]
            if remaining_name:
                user.first_name = remaining_name
                changed_fields = ['first_name']

        if changed_fields:
            user.save(update_fields=changed_fields)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_alter_studentprofile_section'),
    ]

    operations = [
        # Giving the legacy column a temporary default keeps this migration
        # safely reversible even after the column has been removed.
        migrations.AlterField(
            model_name='studentprofile',
            name='full_name',
            field=models.CharField(default='', max_length=150),
        ),
        migrations.RunPython(move_student_names_to_user, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='studentprofile',
            name='full_name',
        ),
    ]
