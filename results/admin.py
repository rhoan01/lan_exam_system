from django.contrib import admin
from .models import ExamAttempt, StudentAnswer, ExamAccessGrant


class StudentAnswerInline(admin.TabularInline):
    model = StudentAnswer
    extra = 0
    readonly_fields = ('question', 'selected_choice', 'text_answer', 'points_earned')


@admin.register(ExamAttempt)
class ExamAttemptAdmin(admin.ModelAdmin):
    list_display = ('student', 'exam', 'score', 'total_points', 'is_submitted', 'tab_switch_count', 'submitted_at')
    list_filter = ('exam', 'is_submitted')
    inlines = [StudentAnswerInline]


@admin.register(ExamAccessGrant)
class ExamAccessGrantAdmin(admin.ModelAdmin):
    list_display = ('student', 'exam', 'redeemed_at')
    list_filter = ('exam',)
