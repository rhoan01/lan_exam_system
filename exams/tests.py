import io
import tempfile

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test import SimpleTestCase
from django.urls import reverse
from PIL import Image

from accounts.models import Program, StudentProfile
from results.models import ExamAttempt

from .models import (
    Exam, ImageIdentificationItem, Question, Subject, validate_question_image,
)
from .forms import ExamForm
from .parsing import BulkImportError, parse_bulk_questions


PROGRAMMING_SAMPLE = """1. Analyze the output.

value = 2

value = value * 5
print(value)

A. 2
B. 5
C. 10 *
D. value * 5

2) Choose the displayed word.
This question text spans two lines.

word = "LAN"
print(word)

A) WAN
B) LAN*
C) MAN
"""


class ProgrammingMultipleChoiceParserTests(SimpleTestCase):
    def test_parses_multiple_questions_and_preserves_code(self):
        parsed = parse_bulk_questions(PROGRAMMING_SAMPLE, max_new_items=10)

        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]['question_type'], 'PMCQ')
        self.assertEqual(parsed[0]['question_text'], 'Analyze the output.')
        self.assertEqual(
            parsed[0]['code_snippet'],
            'value = 2\n\nvalue = value * 5\nprint(value)',
        )
        self.assertEqual(parsed[0]['choices'][-1], ('value * 5', False))
        self.assertEqual([text for text, correct in parsed[0]['choices'] if correct], ['10'])
        self.assertEqual(
            parsed[1]['question_text'],
            'Choose the displayed word.\nThis question text spans two lines.',
        )
        self.assertEqual([text for text, correct in parsed[1]['choices'] if correct], ['LAN'])

    def test_accepts_windows_line_endings(self):
        parsed = parse_bulk_questions(PROGRAMMING_SAMPLE.replace('\n', '\r\n'), max_new_items=10)
        self.assertEqual(len(parsed), 2)
        self.assertIn('\n\n', parsed[0]['code_snippet'])

    def test_rejects_no_correct_choice_with_question_number(self):
        text = """7. What prints?

print(1)

A. 1
B. 2
"""
        with self.assertRaisesRegex(BulkImportError, r"Question 7: exactly one choice"):
            parse_bulk_questions(text, max_new_items=10)

    def test_rejects_multiple_correct_choices_with_question_number(self):
        text = """8. What prints?

print(1)

A. 1 *
B. 2*
"""
        with self.assertRaisesRegex(BulkImportError, r"Question 8: exactly one choice"):
            parse_bulk_questions(text, max_new_items=10)

    def test_rejects_missing_code_with_question_number(self):
        text = """9. What prints?


A. 1 *
B. 2
"""
        with self.assertRaisesRegex(BulkImportError, r"Question 9: missing code"):
            parse_bulk_questions(text, max_new_items=10)

    def test_rejects_missing_choices_with_question_number(self):
        text = """10. What prints?

print(1)
"""
        with self.assertRaisesRegex(BulkImportError, r"Question 10: missing choices"):
            parse_bulk_questions(text, max_new_items=10)

    def test_rejects_missing_question_text_with_question_number(self):
        text = """11.

print(1)

A. 1 *
B. 2
"""
        with self.assertRaisesRegex(BulkImportError, r"Question 11: missing question text"):
            parse_bulk_questions(text, max_new_items=10)

    def test_existing_simple_mcq_format_is_unchanged(self):
        text = """1. What is two plus two?
A. 3
B. 4
Answer Key: B
"""
        parsed = parse_bulk_questions(text, max_new_items=10)
        self.assertEqual(parsed[0]['question_type'], 'MCQ')
        self.assertEqual(parsed[0]['choices'], [('3', False), ('4', True)])


class QMarkedMultipleChoiceParserTests(SimpleTestCase):
    def test_embedded_code_uses_boxed_programming_mcq_and_preserves_indentation(self):
        text = """TYPE: MCQ
Q: What does the loop print?
POINTS: 2

for number in range(1, 3):
    print(number)

A) 1
B) 1 2 *
C) 2
D) Nothing

Q: Which keyword exits a loop?

A) pass
B) continue
C) break *
D) return
"""
        parsed = parse_bulk_questions(text, max_new_items=10)

        self.assertEqual(len(parsed), 2)
        self.assertEqual([item['question_type'] for item in parsed], ['PMCQ', 'MCQ'])
        self.assertEqual(parsed[0]['points'], 2)
        self.assertEqual(parsed[0]['question_text'], 'What does the loop print?')
        self.assertEqual(
            parsed[0]['code_snippet'],
            'for number in range(1, 3):\n    print(number)',
        )
        self.assertEqual(parsed[0]['choices'][1], ('1 2', True))
        self.assertEqual(parsed[1]['points'], 1)
        self.assertEqual(parsed[1]['code_snippet'], '')
        self.assertEqual(parsed[1]['choices'][2], ('break', True))

    def test_q_marked_mcq_requires_exactly_one_starred_choice(self):
        text = """Q: Select an answer.
A) First *
B) Second *
"""
        with self.assertRaisesRegex(BulkImportError, r"Question 1: exactly one choice"):
            parse_bulk_questions(text, max_new_items=10)


def uploaded_png(name='diagram.png', color='white'):
    output = io.BytesIO()
    Image.new('RGB', (8, 8), color=color).save(output, format='PNG')
    return SimpleUploadedFile(name, output.getvalue(), content_type='image/png')


class ImageUploadValidationTests(SimpleTestCase):
    def test_rejects_non_image_bytes_with_allowed_extension(self):
        disguised_file = SimpleUploadedFile(
            'not-really-an-image.png', b'plain text', content_type='image/png'
        )
        with self.assertRaises(ValidationError):
            validate_question_image(disguised_file)


class ExamProgramAssignmentFormTests(TestCase):
    def setUp(self):
        User = get_user_model()
        instructor = User.objects.create_user(
            username='program-form-teacher', password='test-pass', role=User.INSTRUCTOR
        )
        self.subject = Subject.objects.create(
            name='Program Testing', code='PROG101', instructor=instructor
        )
        self.program = Program.objects.create(code='BSIT', name='Information Technology')

    def form_data(self, **overrides):
        data = {
            'title': 'Program-scoped exam',
            'instructions': '',
            'time_limit_minutes': '60',
            'target_programs': [str(self.program.pk)],
            'target_year_levels': ['1st Year'],
            'target_sections': ['C'],
        }
        data.update(overrides)
        return data

    def test_requires_program_assignment_or_explicit_all_programs(self):
        form = ExamForm(data=self.form_data(target_programs=[]))

        self.assertFalse(form.is_valid())
        self.assertIn('target_programs', form.errors)

    def test_saves_selected_target_programs(self):
        form = ExamForm(data=self.form_data())
        self.assertTrue(form.is_valid(), form.errors)
        form.instance.subject = self.subject

        exam = form.save()

        self.assertEqual(list(exam.target_programs.all()), [self.program])
        self.assertFalse(exam.available_to_all_programs)

    def test_explicit_all_programs_clears_specific_targets(self):
        form = ExamForm(data=self.form_data(available_to_all_programs='on'))
        self.assertTrue(form.is_valid(), form.errors)
        form.instance.subject = self.subject

        exam = form.save()

        self.assertTrue(exam.available_to_all_programs)
        self.assertFalse(exam.target_programs.exists())


class ExamResultNameFilterTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.instructor = User.objects.create_user(
            username='filter-teacher', password='test-pass', role=User.INSTRUCTOR
        )
        subject = Subject.objects.create(
            name='Database Systems', code='DB101', instructor=self.instructor
        )
        self.exam = Exam.objects.create(subject=subject, title='Midterm Exam')
        self.program = Program.objects.create(code='BSIT', name='Information Technology')

        self.maria_cruz = self.create_student('S-001', 'Maria Elena', 'Dela Cruz', 'B')
        self.mario_santos = self.create_student('S-002', 'Mario', 'Santos', 'A')
        self.maria_santos = self.create_student('S-003', 'Maria', 'Santos', 'B')

        ExamAttempt.objects.create(
            student=self.maria_cruz, exam=self.exam, is_submitted=True,
            score=8, total_points=10,
        )
        ExamAttempt.objects.create(
            student=self.mario_santos, exam=self.exam, is_submitted=True,
            score=7, total_points=10,
        )
        ExamAttempt.objects.create(student=self.maria_santos, exam=self.exam)
        self.client.force_login(self.instructor)

    def create_student(self, id_number, first_name, last_name, section):
        User = get_user_model()
        student = User.objects.create_user(
            username=id_number, password='test-pass', role=User.STUDENT,
            first_name=first_name, last_name=last_name,
        )
        StudentProfile.objects.create(
            user=student,
            id_number=id_number,
            year_level='1st Year',
            section=section,
            program=self.program,
            course='BSIT',
        )
        return student

    def test_results_filter_first_and_last_names_separately(self):
        response = self.client.get(
            reverse('exams:exam_results', args=[self.exam.id]),
            {'first_name': 'maria', 'last_name': 'cruz'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [attempt.student for attempt in response.context['attempts']],
            [self.maria_cruz],
        )
        self.assertEqual(response.context['in_progress_attempts'], [])
        self.assertContains(response, 'Maria Elena Dela Cruz')
        self.assertNotContains(response, 'Mario Santos')

    def test_results_can_show_one_section_across_attempt_statuses(self):
        response = self.client.get(
            reverse('exams:exam_results', args=[self.exam.id]),
            {'section': 'B'},
        )

        self.assertEqual(
            [attempt.student for attempt in response.context['attempts']],
            [self.maria_cruz],
        )
        self.assertEqual(
            [attempt.student for attempt in response.context['in_progress_attempts']],
            [self.maria_santos],
        )
        self.assertContains(response, 'Section B')
        self.assertNotContains(response, 'Mario Santos')

    def test_results_can_reverse_last_name_order(self):
        response = self.client.get(
            reverse('exams:exam_results', args=[self.exam.id]),
            {'name_order': 'desc'},
        )

        self.assertEqual(
            [attempt.student for attempt in response.context['attempts']],
            [self.mario_santos, self.maria_cruz],
        )
        self.assertContains(response, 'Last name: Z to A')

    def test_csv_export_uses_the_active_name_filter(self):
        response = self.client.get(
            reverse('exams:export_exam_results_csv', args=[self.exam.id]),
            {'last_name': 'santos'},
        )

        content = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn('Mario Santos', content)
        self.assertNotIn('Maria Elena Dela Cruz', content)

    def test_csv_export_uses_the_active_section_filter(self):
        response = self.client.get(
            reverse('exams:export_exam_results_csv', args=[self.exam.id]),
            {'section': 'B'},
        )

        content = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn('Maria Elena Dela Cruz', content)
        self.assertNotIn('Mario Santos', content)


class ImageIdentificationEditorTests(TestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.media_directory.cleanup)
        media_override = self.settings(MEDIA_ROOT=self.media_directory.name)
        media_override.enable()
        self.addCleanup(media_override.disable)

        User = get_user_model()
        self.instructor = User.objects.create_user(
            username='image-teacher', password='test-pass', role=User.INSTRUCTOR
        )
        self.student = User.objects.create_user(
            username='image-student', password='test-pass', role=User.STUDENT,
            first_name='Image', last_name='Student',
        )
        self.program = Program.objects.create(code='BSIT', name='Information Technology')
        StudentProfile.objects.create(
            user=self.student,
            id_number='IMG-001',
            year_level='1st Year',
            section='A',
            program=self.program,
            course='BSIT',
        )
        subject = Subject.objects.create(
            name='Computer Hardware', code='CH101', instructor=self.instructor
        )
        self.exam = Exam.objects.create(subject=subject, title='Diagram Exam')
        self.client.force_login(self.instructor)

    def item_formset_data(self, items, initial=0):
        prefix = 'image_identification_items'
        data = {
            f'{prefix}-TOTAL_FORMS': str(len(items)),
            f'{prefix}-INITIAL_FORMS': str(initial),
            f'{prefix}-MIN_NUM_FORMS': '0',
            f'{prefix}-MAX_NUM_FORMS': '100',
        }
        for index, item in enumerate(items):
            if item.get('id'):
                data[f'{prefix}-{index}-id'] = str(item['id'])
            data[f'{prefix}-{index}-number'] = str(item['number'])
            data[f'{prefix}-{index}-correct_answer'] = item['answer']
            data[f'{prefix}-{index}-alternate_answers'] = item.get('alternates', '')
            data[f'{prefix}-{index}-points'] = str(item.get('points', 1))
        return data

    def question_data(self):
        return {
            'question_type': Question.IMAGE_IDENTIFICATION,
            'question_text': 'Identify each numbered component.',
            'code_snippet': '',
            'code_language': '',
            'points': '1',
            'expected_answer_count': '1',
        }

    def test_create_image_question_with_numbered_items(self):
        data = self.question_data()
        data.update(self.item_formset_data([
            {'number': 2, 'answer': 'RAM slot', 'points': 3},
            {'number': 1, 'answer': 'CPU socket', 'alternates': 'processor socket', 'points': 2},
        ]))
        data['image'] = uploaded_png('My unsafe diagram name.png')

        response = self.client.post(
            reverse('exams:question_create', args=[self.exam.id]), data=data
        )

        self.assertRedirects(response, reverse('exams:exam_detail', args=[self.exam.id]))
        question = Question.objects.get(exam=self.exam)
        self.assertEqual(question.points, 5)
        self.assertRegex(question.image.name, r'^exam_images/\d+/[0-9a-f]{32}\.png$')
        self.assertEqual(
            list(question.image_identification_items.values_list('number', flat=True)),
            [1, 2],
        )

    def test_started_exam_blocks_image_and_number_changes(self):
        question = Question.objects.create(
            exam=self.exam,
            order=1,
            question_type=Question.IMAGE_IDENTIFICATION,
            question_text='Original instructions',
            image=uploaded_png('original.png'),
        )
        first = ImageIdentificationItem.objects.create(
            question=question, number=1, correct_answer='CPU', points=1
        )
        second = ImageIdentificationItem.objects.create(
            question=question, number=2, correct_answer='RAM', points=1
        )
        original_image_name = question.image.name
        ExamAttempt.objects.create(student=self.student, exam=self.exam)

        data = self.question_data()
        data['question_text'] = 'Changed instructions'
        data.update(self.item_formset_data([
            {'id': first.id, 'number': 3, 'answer': 'CPU', 'points': 1},
            {'id': second.id, 'number': 2, 'answer': 'RAM', 'points': 1},
        ], initial=2))

        response = self.client.post(
            reverse('exams:question_edit', args=[question.id]), data=data
        )

        self.assertEqual(response.status_code, 200)
        question.refresh_from_db()
        self.assertEqual(question.question_text, 'Original instructions')
        self.assertEqual(question.image.name, original_image_name)
        self.assertEqual(
            list(question.image_identification_items.values_list('number', flat=True)),
            [1, 2],
        )
        self.assertContains(response, 'Item numbers cannot be added, removed, or changed')

        data = self.question_data()
        data.update(self.item_formset_data([
            {'id': first.id, 'number': 1, 'answer': 'CPU', 'points': 1},
            {'id': second.id, 'number': 2, 'answer': 'RAM', 'points': 1},
        ], initial=2))
        data['image'] = uploaded_png('replacement.png', color='black')
        response = self.client.post(
            reverse('exams:question_edit', args=[question.id]), data=data
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'cannot be replaced after a student has started')
