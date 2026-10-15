from django import forms
from django.forms import inlineformset_factory

from accounts.models import YEAR_LEVEL_CHOICES, SECTION_CHOICES
from .models import Subject, Exam, Question, Choice, AnswerKey, MatchingPair


class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ['code', 'name']
        widgets = {
            'code': forms.TextInput(attrs={'placeholder': 'e.g. IT101'}),
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Introduction to Computing'}),
        }


class ExamForm(forms.ModelForm):
    target_year_levels = forms.MultipleChoiceField(
        choices=YEAR_LEVEL_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Available to Year Level(s)",
        help_text="Leave all unchecked to make this exam available to every year level.",
    )
    target_sections = forms.MultipleChoiceField(
        choices=SECTION_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Available to Section(s)",
        help_text="Leave all unchecked to make this exam available to every section.",
    )

    class Meta:
        model = Exam
        fields = ['title', 'instructions', 'time_limit_minutes', 'is_published', 'shuffle_questions', 'shuffle_choices']
        widgets = {
            'instructions': forms.Textarea(attrs={'rows': 3}),
            'time_limit_minutes': forms.NumberInput(attrs={'min': 1, 'max': 600}),
        }
        help_texts = {
            'time_limit_minutes': 'Adjustable countdown timer shown to students, in minutes.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['target_year_levels'].initial = self.instance.target_year_level_list()
            self.fields['target_sections'].initial = self.instance.target_section_list()

    def save(self, commit=True):
        exam = super().save(commit=False)
        exam.target_year_levels = ','.join(self.cleaned_data.get('target_year_levels', []))
        exam.target_sections = ','.join(self.cleaned_data.get('target_sections', []))
        if commit:
            exam.save()
        return exam


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ['question_type', 'question_text', 'points', 'expected_answer_count']
        widgets = {
            'question_text': forms.Textarea(attrs={'rows': 3}),
            'points': forms.NumberInput(attrs={'min': 1}),
            'expected_answer_count': forms.NumberInput(attrs={'min': 1}),
        }


class QuestionEditForm(forms.ModelForm):
    """Like QuestionForm, but the question TYPE can't be changed once
    created - switching types would orphan existing choices/answer keys.
    Everything else (text, points, expected answer count) is editable."""
    class Meta:
        model = Question
        fields = ['question_text', 'points', 'expected_answer_count']
        widgets = {
            'question_text': forms.Textarea(attrs={'rows': 3}),
            'points': forms.NumberInput(attrs={'min': 1}),
            'expected_answer_count': forms.NumberInput(attrs={'min': 1}),
        }


ChoiceFormSet = inlineformset_factory(
    Question, Choice,
    fields=['choice_text', 'is_correct'],
    extra=4, max_num=8, can_delete=True,
)


class AnswerKeyForm(forms.ModelForm):
    class Meta:
        model = AnswerKey
        fields = ['correct_answers']
        widgets = {
            'correct_answers': forms.Textarea(attrs={
                'rows': 5,
                'placeholder': 'Enter one accepted answer / keyword per line.',
            }),
        }


MatchingPairFormSet = inlineformset_factory(
    Question, MatchingPair,
    fields=['left_text', 'right_text'],
    extra=4, max_num=20, can_delete=True,
)


class MatchingDistractorForm(forms.Form):
    """Extra Column B options with no correct match - one per line, kept as
    a simple textarea rather than its own formset to keep the question
    form manageable."""
    distractors_text = forms.CharField(
        required=False,
        label="Distractor Choices (optional)",
        widget=forms.Textarea(attrs={
            'rows': 4,
            'placeholder': 'One distractor per line (optional) - extra Column B options with no correct match.',
        }),
    )


class BulkImportForm(forms.Form):
    questions_text = forms.CharField(
        label="Paste your questions",
        required=False,
        widget=forms.Textarea(attrs={'rows': 16, 'placeholder': 'TYPE: MCQ\nQ: ...\nPOINTS: 2\nA) ...\nB) ... *\n'}),
    )
    file = forms.FileField(label="...or upload a .txt file", required=False)
    replace_existing = forms.BooleanField(
        label="Replace all existing questions with this import",
        required=False,
        help_text=(
            "If checked, every current question for this exam (and its choices/answer "
            "keys) will be permanently deleted first, then replaced with this import. "
            "If unchecked, these questions are simply added to the existing ones."
        ),
    )

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('questions_text', '').strip() and not cleaned.get('file'):
            raise forms.ValidationError("Paste your questions in the box, or upload a .txt file, before submitting.")
        return cleaned
