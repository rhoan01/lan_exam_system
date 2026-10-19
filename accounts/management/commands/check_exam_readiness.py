import os

from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Verify that the exam server is connected to a suitably configured MySQL database."

    def handle(self, *args, **options):
        if connection.vendor != 'mysql':
            raise CommandError(
                f"Refusing to start: active database is {connection.vendor!r}, not MySQL."
            )

        try:
            worker_threads = int(os.environ.get('WAITRESS_THREADS', '32'))
        except ValueError as exc:
            raise CommandError('WAITRESS_THREADS must be an integer.') from exc

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT DATABASE(), CURRENT_USER(), @@max_connections, "
                "@@innodb_buffer_pool_size, VERSION()"
            )
            database_name, database_user, max_connections, buffer_pool, version = cursor.fetchone()
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = DATABASE() AND engine <> 'InnoDB' "
                "AND table_name IN ('results_examattempt', 'results_studentanswer')"
            )
            non_innodb_tables = cursor.fetchone()[0]

        expected_database = os.environ.get('DB_NAME', 'examsystem')
        if database_name != expected_database:
            raise CommandError(
                f"Connected to database {database_name!r}; expected {expected_database!r}."
            )

        required_connections = worker_threads + 10
        if max_connections < required_connections:
            raise CommandError(
                f"MySQL max_connections is {max_connections}; at least "
                f"{required_connections} is required for {worker_threads} web threads."
            )

        if non_innodb_tables:
            raise CommandError('Exam attempt/answer tables must use the InnoDB storage engine.')

        self.stdout.write(self.style.SUCCESS('MySQL deployment readiness check passed.'))
        self.stdout.write(f'  Database: {database_name}')
        self.stdout.write(f'  Application user: {database_user}')
        self.stdout.write(f'  MySQL version: {version}')
        self.stdout.write(f'  Max connections: {max_connections}')
        self.stdout.write(f'  InnoDB buffer pool: {buffer_pool // (1024 * 1024)} MiB')
        self.stdout.write(f'  Waitress threads: {worker_threads}')
