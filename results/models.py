from django.conf import settings
from django.db import models

from exams.models import Exam, Question, Choice


class ExamAttempt(models.Model):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='attempts',
        limit_choices_to={'role': 'student'},
    )
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='attempts')
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    is_submitted = models.BooleanField(default=False)
    score = models.FloatField(default=0)
    total_points = models.FloatField(default=0)
    tab_switch_count = models.PositiveIntegerField(
        default=0, help_text="Number of times the student left/switched away from this exam's tab."
    )
    extra_time_seconds = models.PositiveIntegerField(
        default=0,
        help_text="Extra time (in seconds) an instructor has granted this attempt, e.g. to make up for a power/network interruption.",
    )
    current_question_index = models.PositiveIntegerField(
        default=0,
        help_text="Last question the student had open - used to resume at the same item after a reload or an instructor-reopened attempt.",
    )

    class Meta:
        unique_together = ('student', 'exam')

    def percentage(self):
        if not self.total_points:
            return 0
        return round((self.score / self.total_points) * 100)

    def extra_time_minutes(self):
        return self.extra_time_seconds // 60

    def __str__(self):
        return f"{self.student} - {self.exam} - {self.score}/{self.total_points}"


class ExamAccessGrant(models.Model):
    """Records that a student outside an exam's target program/class has
    redeemed the exam's access code and is allowed to take it anyway
    (e.g. an irregular student)."""
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='exam_access_grants',
        limit_choices_to={'role': 'student'},
    )
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='access_grants')
    redeemed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'exam')

    def __str__(self):
        return f"{self.student} unlocked {self.exam}"


class StudentAnswer(models.Model):
    attempt = models.ForeignKey(ExamAttempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_choice = models.ForeignKey(Choice, on_delete=models.SET_NULL, null=True, blank=True)
    text_answer = models.TextField(blank=True)
    needs_manual_review = models.BooleanField(default=False)
    points_earned = models.FloatField(default=0)

    class Meta:
        unique_together = ('attempt', 'question')
