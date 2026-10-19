from types import SimpleNamespace

from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase
from django.test.client import RequestFactory
from django.urls import reverse

from accounts.models import Program, StudentProfile
from exams.models import Choice, Exam, ImageIdentificationItem, Question, Subject
from .grading import grade_answer, matches_accepted_answer, normalize_answer


class ProgrammingMultipleChoiceGradingTests(SimpleTestCase):
    def test_programming_mcq_uses_normal_choice_grading(self):
        question = SimpleNamespace(
            question_type=Question.PROGRAMMING_MCQ,
            points=3,
        )

        self.assertEqual(
            grade_answer(question, selected_choice=SimpleNamespace(is_correct=True)),
            (3, False),
        )
        self.assertEqual(
            grade_answer(question, selected_choice=SimpleNamespace(is_correct=False)),
            (0, False),
        )

    def test_student_page_escapes_code_and_hides_correctness(self):
        request = RequestFactory().get('/')
        request.user = AnonymousUser()
        exam = SimpleNamespace(
            id=1,
            title='Code Exam',
            subject=SimpleNamespace(code='CS101'),
            instructions='',
        )
        question = Question(
            id=7,
            question_type=Question.PROGRAMMING_MCQ,
            question_text='What prints?',
            code_snippet='<script>alert(1)</script>\n\tprint(2)',
            code_language='Python',
            points=1,
        )
        question.saved_choice_id = None
        question.shuffled_choices = [
            Choice(id=8, choice_text='2', is_correct=True),
            Choice(id=9, choice_text='3', is_correct=False),
        ]

        html = render_to_string(
            'results/take_exam.html',
            {
                'exam': exam,
                'questions': [question],
                'attempt': SimpleNamespace(id=3),
                'remaining_seconds': 60,
                'resume_index': 0,
            },
            request=request,
        )

        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', html)
        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertNotIn('is_correct', html)
        self.assertNotIn('>Correct<', html)
        self.assertIn('class="code-lines"', html)


class ImageIdentificationMatchingTests(SimpleTestCase):
    def test_normalization_is_case_and_whitespace_insensitive(self):
        self.assertEqual(normalize_answer('  CPU   Socket\n'), 'cpu socket')
        self.assertTrue(matches_accepted_answer(' PROCESSOR   socket ', ['CPU socket', 'Processor Socket']))

    def test_blank_never_matches(self):
        self.assertFalse(matches_accepted_answer('', ['CPU socket']))
        self.assertFalse(matches_accepted_answer('   ', ['', '   ']))


class ImageIdentificationIntegrationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.instructor = User.objects.create_user(
            username='teacher', password='test-pass', role=User.INSTRUCTOR
        )
        self.student = User.objects.create_user(
            username='student', password='test-pass', role=User.STUDENT,
            first_name='Test', last_name='Student',
        )
        self.program = Program.objects.create(code='BSIT', name='Information Technology')
        StudentProfile.objects.create(
            user=self.student,
            id_number='2026-0001',
            year_level='1st Year',
            section='A',
            program=self.program,
            course='BSIT',
        )
        subject = Subject.objects.create(
            name='Hardware', code='HW101', instructor=self.instructor
        )
        self.exam = Exam.objects.create(
            subject=subject, title='Parts', is_published=True, shuffle_questions=False
        )
        self.exam.target_programs.add(self.program)
        self.question = Question.objects.create(
            exam=self.exam,
            order=1,
            question_type=Question.IMAGE_IDENTIFICATION,
            question_text='Identify the numbered parts.',
            image='exam_images/test-diagram.png',
            points=1,
        )
        ImageIdentificationItem.objects.create(
            question=self.question,
            number=1,
            correct_answer='CPU socket',
            alternate_answers='processor socket',
            points=2,
        )
        ImageIdentificationItem.objects.create(
            question=self.question,
            number=2,
            correct_answer='RAM slot',
            alternate_answers='DIMM slot',
            points=3,
        )

    def test_grading_awards_partial_credit_per_number(self):
        self.question.refresh_from_db()
        score, needs_review = grade_answer(
            self.question,
            text_answer='{"1": "  PROCESSOR   SOCKET ", "2": "PCIe slot"}',
        )
        self.assertEqual(score, 2)
        self.assertFalse(needs_review)
        self.assertEqual(self.question.points, 5)

    def test_student_exam_page_does_not_leak_answer_key(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('results:take_exam', args=[self.exam.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="question_%s_item_1"' % self.question.id)
        self.assertNotContains(response, 'CPU socket')
        self.assertNotContains(response, 'processor socket')
        self.assertNotContains(response, 'RAM slot')
        self.assertNotContains(response, 'DIMM slot')

    def test_numbered_answers_autosave_and_restore(self):
        self.client.force_login(self.student)
        self.client.get(reverse('results:take_exam', args=[self.exam.id]))

        response = self.client.post(
            reverse('results:autosave_exam', args=[self.exam.id]),
            {
                f'question_{self.question.id}_item_1': 'My first answer',
                f'question_{self.question.id}_item_2': 'My second answer',
                'current_index': '0',
            },
        )
        self.assertEqual(response.json()['status'], 'ok')

        response = self.client.get(reverse('results:take_exam', args=[self.exam.id]))
        self.assertContains(response, 'value="My first answer"')
        self.assertContains(response, 'value="My second answer"')


class ProgramExamAccessTests(TestCase):
    def setUp(self):
        User = get_user_model()
        instructor = User.objects.create_user(
            username='program-teacher', password='test-pass', role=User.INSTRUCTOR
        )
        self.it = Program.objects.create(code='BSIT', name='Information Technology')
        self.crim = Program.objects.create(code='BSCRIM', name='Criminology')
        subject = Subject.objects.create(
            name='Networking', code='NET101', instructor=instructor
        )
        self.exam = Exam.objects.create(
            subject=subject,
            title='IT Network Exam',
            is_published=True,
            target_year_levels='1st Year',
            target_sections='C',
        )
        self.exam.target_programs.add(self.it)
        self.it_student = self.create_student('IT-001', self.it)
        self.crim_student = self.create_student('CRIM-001', self.crim)

    @staticmethod
    def create_student(username, program):
        User = get_user_model()
        student = User.objects.create_user(
            username=username,
            password='test-pass',
            role=User.STUDENT,
            first_name='Test',
            last_name=program.code,
        )
        StudentProfile.objects.create(
            user=student,
            id_number=username,
            year_level='1st Year',
            section='C',
            program=program,
            course=program.code,
        )
        return student

    def test_matching_program_student_can_see_and_open_exam(self):
        self.client.force_login(self.it_student)

        dashboard = self.client.get(reverse('results:student_dashboard'))
        exam_page = self.client.get(reverse('results:take_exam', args=[self.exam.id]))

        self.assertContains(dashboard, self.exam.title)
        self.assertEqual(exam_page.status_code, 200)

    def test_same_year_and_section_but_different_program_is_denied(self):
        self.client.force_login(self.crim_student)

        dashboard = self.client.get(reverse('results:student_dashboard'))
        exam_page = self.client.get(reverse('results:take_exam', args=[self.exam.id]))

        self.assertNotContains(dashboard, self.exam.title)
        self.assertRedirects(exam_page, reverse('results:student_dashboard'))
        self.assertFalse(
            self.exam.attempts.filter(student=self.crim_student).exists()
        )

    def test_exam_without_program_assignment_fails_closed(self):
        self.exam.target_programs.clear()
        self.client.force_login(self.it_student)

        dashboard = self.client.get(reverse('results:student_dashboard'))

        self.assertNotContains(dashboard, self.exam.title)

    def test_explicit_all_programs_setting_allows_other_program(self):
        self.exam.target_programs.clear()
        self.exam.available_to_all_programs = True
        self.exam.save(update_fields=['available_to_all_programs'])
        self.client.force_login(self.crim_student)

        dashboard = self.client.get(reverse('results:student_dashboard'))

        self.assertContains(dashboard, self.exam.title)
