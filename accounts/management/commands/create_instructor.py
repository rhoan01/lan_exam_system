from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create an Instructor/Admin account (username + password)."

    def add_arguments(self, parser):
        parser.add_argument('username', type=str)
        parser.add_argument('password', type=str)
        parser.add_argument('--first_name', type=str, default='')
        parser.add_argument('--last_name', type=str, default='')

    def handle(self, *args, **options):
        User = get_user_model()
        username = options['username']
        if User.objects.filter(username=username).exists():
            raise CommandError(f"User '{username}' already exists.")
        user = User.objects.create_user(
            username=username,
            password=options['password'],
            first_name=options['first_name'],
            last_name=options['last_name'],
        )
        user.role = User.INSTRUCTOR
        user.is_staff = True
        user.save()
        self.stdout.write(self.style.SUCCESS(f"Instructor account '{username}' created."))
