"""
Creates a timestamped JSON backup of all examination data: student
accounts, instructor accounts, subjects, exams, questions, choices,
answer keys, exam attempts, and student answers.

This uses Django's own dumpdata mechanism, so it works identically
whether the project is running on SQLite or MySQL/MariaDB — no
database-specific backup tool (like mysqldump) is required, though
you may still want to use mysqldump as a second, complementary
full-database backup if you're on MySQL (see deployment/README_DEPLOYMENT.md).

Usage:
    python manage.py backup_data
    python manage.py backup_data --output-dir=D:\\ExamBackups

This command is read-only with respect to your data — it never
deletes or modifies anything, so it's safe to run at any time,
including while an exam is in progress.
"""
import os
from datetime import datetime

from django.core.management import call_command
from django.core.management.base import BaseCommand


APPS_TO_BACK_UP = [
    'accounts',
    'exams',
    'results',
]


class Command(BaseCommand):
    help = "Back up all examination data (users, subjects, exams, questions, attempts, scores) to a JSON file."

    def add_arguments(self, parser):
        parser.add_argument(
            '--output-dir', type=str, default=None,
            help="Folder to save the backup file in (default: a 'backups' folder in the project root).",
        )

    def handle(self, *args, **options):
        output_dir = options['output_dir']
        if not output_dir:
            from django.conf import settings
            output_dir = os.path.join(settings.BASE_DIR, 'backups')

        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'exam_backup_{timestamp}.json'
        filepath = os.path.join(output_dir, filename)

        self.stdout.write(f"Backing up: {', '.join(APPS_TO_BACK_UP)} ...")

        with open(filepath, 'w', encoding='utf-8') as f:
            call_command(
                'dumpdata',
                *APPS_TO_BACK_UP,
                indent=2,
                stdout=f,
            )

        size_kb = os.path.getsize(filepath) / 1024
        self.stdout.write(self.style.SUCCESS(
            f"Backup saved to: {filepath} ({size_kb:.1f} KB)"
        ))
        self.stdout.write(
            "To restore this backup later, run:\n"
            f"    python manage.py loaddata \"{filepath}\""
        )
