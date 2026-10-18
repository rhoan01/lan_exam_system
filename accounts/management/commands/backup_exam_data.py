import os
from datetime import datetime

from django.core import management
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Back up all examination data (accounts, subjects, exams, questions, "
        "answers, attempts, results) to a single JSON file. Works the same "
        "way regardless of whether the database is SQLite or MySQL/MariaDB, "
        "so it's the recommended way to back up before an examination.\n\n"
        "Usage:\n"
        "  python manage.py backup_exam_data\n"
        "  python manage.py backup_exam_data --output backups\\before_exam.json"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--output', type=str, default=None,
            help="Output file path. Defaults to backups/exam_backup_<timestamp>.json",
        )

    def handle(self, *args, **options):
        output_path = options['output']
        if not output_path:
            os.makedirs('backups', exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = os.path.join('backups', f'exam_backup_{timestamp}.json')
        else:
            out_dir = os.path.dirname(output_path)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)

        # Excludes Django's own bookkeeping tables (sessions, content types,
        # permissions) - only the actual examination data is included.
        apps_to_dump = ['accounts', 'exams', 'results']

        with open(output_path, 'w', encoding='utf-8') as f:
            management.call_command(
                'dumpdata', *apps_to_dump,
                indent=2,
                use_natural_foreign_keys=True,
                stdout=f,
            )

        self.stdout.write(self.style.SUCCESS(f"Backup written to {output_path}"))
        self.stdout.write(
            "To restore this backup later, run:\n"
            f"  python manage.py loaddata {output_path}"
        )
