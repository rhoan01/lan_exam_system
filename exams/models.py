import random
import string
import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from PIL import Image, UnidentifiedImageError

MAX_ITEMS_PER_EXAM = 100
ACCESS_CODE_LENGTH = 8
MAX_QUESTION_IMAGE_SIZE = 5 * 1024 * 1024


def image_identification_upload_to(instance, filename):
    """Keep instructor filenames off disk and group uploads by exam."""
    extension = Path(filename).suffix.lower()
    return f'exam_images/{instance.exam_id}/{uuid.uuid4().hex}{extension}'


def validate_question_image(uploaded_file):
    """Validate image bytes as well as the browser-provided filename."""
    if uploaded_file.size > MAX_QUESTION_IMAGE_SIZE:
        raise ValidationError("Image files must be 5 MB or smaller.")

    was_closed = uploaded_file.closed
    position = uploaded_file.tell()
    try:
        uploaded_file.seek(0)
        with Image.open(uploaded_file) as image:
            if image.format not in {'PNG', 'JPEG', 'WEBP'}:
                raise ValidationError("Upload a PNG, JPG, JPEG, or WEBP image.")
            image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise ValidationError("The uploaded file is not a valid image.")
    finally:
        if was_closed:
            uploaded_file.close()
        elif not uploaded_file.closed:
            uploaded_file.seek(position)


class Subject(models.Model):
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=30, unique=True)
    instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subjects',
        limit_choices_to={'role': 'instructor'},
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"


class Exam(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='exams')
    title = models.CharField(max_length=200)
    instructions = models.TextField(blank=True)
    time_limit_minutes = models.PositiveIntegerField(
        default=60, help_text="Adjustable time limit for this exam, in minutes."
    )
    is_published = models.BooleanField(
        default=False, db_index=True,
        help_text="Students can only see and take published exams."
    )
    shuffle_questions = models.BooleanField(
        default=True,
        help_text="Show questions in a different random order to each student (helps prevent copying).",
    )
    shuffle_choices = models.BooleanField(
        default=True,
        help_text="Show multiple-choice options in a different random order to each student.",
    )
    target_year_levels = models.CharField(
        max_length=100, blank=True,
        help_text=(
            "Comma-separated year levels this exam is available to "
            "(e.g. '1st Year,2nd Year'). Leave blank for all year levels."
        ),
    )
    target_sections = models.CharField(
        max_length=50, blank=True,
        help_text=(
            "Comma-separated sections this exam is available to (e.g. 'A,C'). "
            "Leave blank for all sections."
        ),
    )
    access_code = models.CharField(
        max_length=ACCESS_CODE_LENGTH, blank=True, null=True, unique=True,
        help_text=(
            "Auto-generated when the exam is published. Lets an irregular "
            "student outside the target year level(s) unlock this exam."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def total_items(self):
        return self.questions.count()

    def total_points(self):
        return sum(q.points for q in self.questions.all())

    def has_room_for_more_questions(self):
        return self.total_items() < MAX_ITEMS_PER_EXAM

    def target_year_level_list(self):
        return [y.strip() for y in self.target_year_levels.split(',') if y.strip()]

    def is_available_to_year(self, year_level):
        """An exam with no target year levels set is open to everyone."""
        targets = self.target_year_level_list()
        return not targets or year_level in targets

    def target_section_list(self):
        return [s.strip() for s in self.target_sections.split(',') if s.strip()]

    def is_available_to_section(self, section):
        """An exam with no target sections set is open to every section."""
        targets = self.target_section_list()
        return not targets or section in targets

    def is_available_to_student(self, profile):
        """Combines the year-level and section checks - both must pass."""
        return self.is_available_to_year(profile.year_level) and self.is_available_to_section(profile.section)

    def generate_access_code(self):
        alphabet = string.ascii_uppercase + string.digits
        while True:
            code = ''.join(random.choices(alphabet, k=ACCESS_CODE_LENGTH))
            if not Exam.objects.filter(access_code=code).exists():
                return code

    def __str__(self):
        return f"{self.title} ({self.subject.code})"


class Question(models.Model):
    MCQ = 'MCQ'
    PROGRAMMING_MCQ = 'PMCQ'
    TF = 'TF'
    ENUM = 'ENUM'
    IDENT = 'IDENT'
    CASE = 'CASE'
    MATCH = 'MATCH'
    IMAGE_IDENTIFICATION = 'image_identification'
    TYPE_CHOICES = (
        (MCQ, 'Multiple Choice'),
        (PROGRAMMING_MCQ, 'Programming Multiple Choice'),
        (TF, 'True or False'),
        (ENUM, 'Enumeration'),
        (IDENT, 'Identification'),
        (CASE, 'Case Analysis (essay/typed answer)'),
        (MATCH, 'Matching Type'),
        (IMAGE_IDENTIFICATION, 'Image Identification'),
    )
    CHOICE_BASED_TYPES = (MCQ, PROGRAMMING_MCQ, TF)

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='questions')
    order = models.PositiveIntegerField(default=1)
    question_type = models.CharField(max_length=24, choices=TYPE_CHOICES)
    question_text = models.TextField()
    image = models.ImageField(
        upload_to=image_identification_upload_to,
        blank=True,
        validators=[
            FileExtensionValidator(allowed_extensions=['png', 'jpg', 'jpeg', 'webp']),
            validate_question_image,
        ],
        help_text="Image Identification only: PNG, JPG, JPEG, or WEBP; maximum 5 MB.",
    )
    code_snippet = models.TextField(
        blank=True,
        help_text="Programming Multiple Choice only: code shown between the question and choices.",
    )
    code_language = models.CharField(
        max_length=30, blank=True,
        help_text="Optional language label, such as Python, C#, or Java.",
    )
    points = models.PositiveIntegerField(default=1)
    expected_answer_count = models.PositiveIntegerField(
        default=1, help_text="Enumeration only: how many separate answers are expected."
    )

    class Meta:
        ordering = ['order']

    def clean(self):
        if self.exam_id and not self.pk:
            if self.exam.total_items() >= MAX_ITEMS_PER_EXAM:
                raise ValidationError(
                    f"This exam already has the maximum of {MAX_ITEMS_PER_EXAM} items."
                )
        if self.question_type == self.IMAGE_IDENTIFICATION and not self.image:
            raise ValidationError({'image': "Upload the numbered image for this question."})

    def is_choice_based(self):
        """Choice-based questions work by picking one fixed Choice row."""
        return self.question_type in self.CHOICE_BASED_TYPES

    def is_objective(self):
        """Can be graded with exact/near-exact matching."""
        return self.question_type in (
            self.MCQ, self.PROGRAMMING_MCQ, self.TF, self.IDENT,
            self.IMAGE_IDENTIFICATION,
        )

    def code_lines(self):
        """Return code as display lines without changing its whitespace."""
        return self.code_snippet.split('\n')

    def column_b_pool(self):
        """All Column B options for a Matching question: each pair's correct
        answer, plus any distractors - the full pool a student picks from."""
        pairs = list(self.matching_pairs.all())
        distractors = list(self.matching_distractors.all())
        return [p.right_text for p in pairs] + [d.text for d in distractors]

    def __str__(self):
        return f"Q{self.order} ({self.get_question_type_display()}): {self.question_text[:50]}"


class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choices')
    choice_text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return self.choice_text


class AnswerKey(models.Model):
    """Instructor-uploaded answer key for text-based questions:
    Identification, Enumeration, and Case Analysis.
    """
    question = models.OneToOneField(Question, on_delete=models.CASCADE, related_name='answer_key')
    correct_answers = models.TextField(
        help_text=(
            "Identification: one accepted answer per line (any line matching counts as correct). "
            "Enumeration: one expected answer per line. "
            "Case Analysis: one key concept/keyword per line, used for keyword-matching auto-grading."
        )
    )

    def answers_list(self):
        return [a.strip() for a in self.correct_answers.splitlines() if a.strip()]

    def __str__(self):
        return f"Answer key for {self.question}"


class MatchingPair(models.Model):
    """One Column A item and its correct Column B answer, for a Matching
    Type question. Column B is shuffled per-student at exam time - see
    Question.column_b_pool() and the shuffling logic in results/views.py."""
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='matching_pairs')
    order = models.PositiveIntegerField(default=1)
    left_text = models.CharField(max_length=255, help_text="Column A item.")
    right_text = models.CharField(max_length=255, help_text="The correct Column B answer for this item.")

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.left_text} → {self.right_text}"


class MatchingDistractor(models.Model):
    """An extra Column B option with no correct Column A match - makes
    Matching Type questions harder to guess by elimination."""
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='matching_distractors')
    text = models.CharField(max_length=255)

    def __str__(self):
        return self.text


class ImageIdentificationItem(models.Model):
    """One numbered label and its accepted answers within an image question."""
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name='image_identification_items'
    )
    number = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    correct_answer = models.CharField(max_length=255)
    alternate_answers = models.TextField(
        blank=True,
        help_text="Optional alternate accepted answers, one per line.",
    )
    points = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])

    class Meta:
        ordering = ['number']
        constraints = [
            models.UniqueConstraint(
                fields=['question', 'number'],
                name='unique_image_identification_number_per_question',
            ),
        ]

    def accepted_answers(self):
        alternates = [answer.strip() for answer in self.alternate_answers.splitlines() if answer.strip()]
        return [self.correct_answer.strip(), *alternates]

    def __str__(self):
        return f"{self.question} - #{self.number}: {self.correct_answer}"


def _sync_image_question_points(question_id):
    total = ImageIdentificationItem.objects.filter(question_id=question_id).aggregate(
        total=models.Sum('points')
    )['total'] or 0
    if total:
        Question.objects.filter(
            pk=question_id, question_type=Question.IMAGE_IDENTIFICATION
        ).update(points=total)


@receiver(post_save, sender=ImageIdentificationItem)
@receiver(post_delete, sender=ImageIdentificationItem)
def sync_image_question_points(sender, instance, **kwargs):
    _sync_image_question_points(instance.question_id)


@receiver(pre_save, sender=Question)
def remember_replaced_question_image(sender, instance, **kwargs):
    if not instance.pk:
        return
    old_name = sender.objects.filter(pk=instance.pk).values_list('image', flat=True).first()
    new_name = instance.image.name if instance.image else ''
    instance._replaced_image_name = old_name if old_name and old_name != new_name else ''


@receiver(post_save, sender=Question)
def delete_replaced_question_image(sender, instance, **kwargs):
    old_name = getattr(instance, '_replaced_image_name', '')
    if old_name:
        storage = instance._meta.get_field('image').storage
        transaction.on_commit(lambda: storage.delete(old_name))


@receiver(post_delete, sender=Question)
def delete_question_image(sender, instance, **kwargs):
    if instance.image:
        storage = instance.image.storage
        image_name = instance.image.name
        transaction.on_commit(lambda: storage.delete(image_name))
