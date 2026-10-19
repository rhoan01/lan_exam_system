from django.contrib import admin
from .models import (
    Subject, Exam, Question, Choice, AnswerKey, MatchingPair, MatchingDistractor,
    ImageIdentificationItem,
)


class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 2


class MatchingPairInline(admin.TabularInline):
    model = MatchingPair
    extra = 2


class MatchingDistractorInline(admin.TabularInline):
    model = MatchingDistractor
    extra = 1


class ImageIdentificationItemInline(admin.TabularInline):
    model = ImageIdentificationItem
    extra = 1


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'instructor')


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'subject', 'time_limit_minutes', 'is_published',
        'available_to_all_programs', 'target_year_levels', 'access_code',
    )
    list_filter = ('is_published', 'available_to_all_programs', 'subject', 'target_programs')
    filter_horizontal = ('target_programs',)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('exam', 'order', 'question_type', 'question_text', 'points')
    inlines = [
        ChoiceInline, MatchingPairInline, MatchingDistractorInline,
        ImageIdentificationItemInline,
    ]


admin.site.register(Choice)
admin.site.register(AnswerKey)
admin.site.register(MatchingPair)
admin.site.register(MatchingDistractor)
admin.site.register(ImageIdentificationItem)
