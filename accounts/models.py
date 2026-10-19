from django.contrib.auth.models import AbstractUser
from django.db import models

YEAR_LEVEL_CHOICES = (
    ('1st Year', '1st Year'),
    ('2nd Year', '2nd Year'),
    ('3rd Year', '3rd Year'),
    ('4th Year', '4th Year'),
)

SECTION_CHOICES = (
    ('A', 'Section A'),
    ('B', 'Section B'),
    ('C', 'Section C'),
    ('D', 'Section D'),
    ('E', 'Section E'),
    ('F', 'Section F'),
)


class Program(models.Model):
    """A trusted academic program used to scope student exam access."""

    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        self.name = self.name.strip()
        super().save(*args, **kwargs)

    def __str__(self):
        if self.name.casefold() == self.code.casefold():
            return self.code
        return f"{self.code} — {self.name}"


class User(AbstractUser):
    STUDENT = 'student'
    INSTRUCTOR = 'instructor'
    ROLE_CHOICES = (
        (STUDENT, 'Student'),
        (INSTRUCTOR, 'Instructor'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=STUDENT)

    def save(self, *args, **kwargs):
        # Any account created through createsuperuser / the admin site is
        # automatically treated as an Instructor/Administrator account.
        if self.is_superuser:
            self.role = self.INSTRUCTOR
        super().save(*args, **kwargs)

    def is_student(self):
        return self.role == self.STUDENT

    def is_instructor(self):
        return self.role == self.INSTRUCTOR

    def __str__(self):
        return self.get_full_name() or self.username


class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    id_number = models.CharField(max_length=30, unique=True)
    year_level = models.CharField(max_length=20, choices=YEAR_LEVEL_CHOICES)
    section = models.CharField(max_length=20, choices=SECTION_CHOICES)
    # Retained as a non-editable compatibility snapshot for old exports and
    # migrations. Authorization uses the Program foreign key below.
    course = models.CharField(max_length=100, editable=False)
    program = models.ForeignKey(
        Program, on_delete=models.PROTECT, related_name='students'
    )

    def __str__(self):
        return f"{self.id_number} - {self.user.get_full_name() or self.user.username}"
