from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.db.models import Q

from accounts.models import Program, YEAR_LEVEL_CHOICES, SECTION_CHOICES
from .models import (
    Subject, Exam, Question, Choice, AnswerKey, MatchingPair,
    ImageIdentificationItem,
)


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
        fields = [
            'title', 'instructions', 'time_limit_minutes',
            'available_to_all_programs', 'target_programs',
            'is_published', 'shuffle_questions', 'shuffle_choices',
        ]
        widgets = {
            'instructions': forms.Textarea(attrs={'rows': 3}),
            'time_limit_minutes': forms.NumberInput(attrs={'min': 1, 'max': 600}),
            'target_programs': forms.CheckboxSelectMultiple,
        }
        help_texts = {
            'time_limit_minutes': 'Adjustable countdown timer shown to students, in minutes.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        program_filter = Q(is_active=True)
        if self.instance and self.instance.pk:
            program_filter |= Q(exams=self.instance)
            self.fields['target_year_levels'].initial = self.instance.target_year_level_list()
            self.fields['target_sections'].initial = self.instance.target_section_list()
        self.fields['target_programs'].queryset = Program.objects.filter(
            program_filter
        ).distinct()

    def save(self, commit=True):
        exam = super().save(commit=False)
        exam.target_year_levels = ','.join(self.cleaned_data.get('target_year_levels', []))
        exam.target_sections = ','.join(self.cleaned_data.get('target_sections', []))
        if commit:
            exam.save()
            self.save_m2m()
        return exam

    def clean(self):
        cleaned = super().clean()
        all_programs = cleaned.get('available_to_all_programs')
        target_programs = cleaned.get('target_programs')
        if not all_programs and not target_programs:
            self.add_error(
                'target_programs',
                "Select at least one program, or explicitly choose all programs.",
            )
        if all_programs:
            cleaned['target_programs'] = []
        return cleaned


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = [
            'question_type', 'question_text', 'image', 'code_snippet', 'code_language',
            'points', 'expected_answer_count',
        ]
        widgets = {
            'question_text': forms.Textarea(attrs={'rows': 3}),
            'image': forms.FileInput(attrs={
                'accept': '.png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp',
            }),
            'code_snippet': forms.Textarea(attrs={
                'rows': 10,
                'spellcheck': 'false',
                'placeholder': 'Paste the code exactly as students should see it.',
            }),
            'code_language': forms.TextInput(attrs={'placeholder': 'e.g. Python'}),
            'points': forms.NumberInput(attrs={'min': 1}),
            'expected_answer_count': forms.NumberInput(attrs={'min': 1}),
        }

    def clean(self):
        cleaned = super().clean()
        if (
            cleaned.get('question_type') == Question.IMAGE_IDENTIFICATION
            and not cleaned.get('image')
        ):
            self.add_error('image', "Upload the numbered image for this question.")
        return cleaned


class QuestionEditForm(forms.ModelForm):
    """Like QuestionForm, but the question TYPE can't be changed once
    created - switching types would orphan existing choices/answer keys.
    Everything else (text, points, expected answer count) is editable."""
    class Meta:
        model = Question
        fields = ['question_text', 'image', 'code_snippet', 'code_language', 'points', 'expected_answer_count']
        widgets = {
            'question_text': forms.Textarea(attrs={'rows': 3}),
            'image': forms.FileInput(attrs={
                'accept': '.png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp',
            }),
            'code_snippet': forms.Textarea(attrs={
                'rows': 10,
                'spellcheck': 'false',
                'placeholder': 'Paste the code exactly as students should see it.',
            }),
            'code_language': forms.TextInput(attrs={'placeholder': 'e.g. Python'}),
            'points': forms.NumberInput(attrs={'min': 1}),
            'expected_answer_count': forms.NumberInput(attrs={'min': 1}),
        }

    def __init__(self, *args, image_locked=False, **kwargs):
        self.image_locked = image_locked
        super().__init__(*args, **kwargs)
        self.fields['image'].required = False

    def clean_image(self):
        if self.image_locked and self.files.get('image'):
            raise forms.ValidationError(
                "The image cannot be replaced after a student has started this exam."
            )
        image = self.cleaned_data.get('image')
        if self.instance.question_type == Question.IMAGE_IDENTIFICATION and not image:
            raise forms.ValidationError("This question must have an image.")
        return image


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


class BaseImageIdentificationItemFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        numbers = []
        item_count = 0
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get('DELETE'):
                continue
            number = form.cleaned_data.get('number')
            answer = (form.cleaned_data.get('correct_answer') or '').strip()
            if number is None and not answer:
                continue
            item_count += 1
            if not answer:
                form.add_error('correct_answer', "Enter a correct answer.")
            if number in numbers:
                form.add_error('number', "Each number must be unique within the question.")
            numbers.append(number)

        if not item_count:
            raise forms.ValidationError("Add at least one numbered item.")


ImageIdentificationItemFormSet = inlineformset_factory(
    Question,
    ImageIdentificationItem,
    formset=BaseImageIdentificationItemFormSet,
    fields=['number', 'correct_answer', 'alternate_answers', 'points'],
    widgets={
        'number': forms.NumberInput(attrs={'min': 1, 'placeholder': '#'}),
        'correct_answer': forms.TextInput(attrs={'placeholder': 'Correct answer'}),
        'alternate_answers': forms.Textarea(attrs={
            'rows': 2,
            'placeholder': 'Alternate answers (one per line)',
        }),
        'points': forms.NumberInput(attrs={'min': 1}),
    },
    extra=3,
    max_num=100,
    can_delete=True,
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
