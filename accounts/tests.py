from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Program, StudentProfile


class StudentRegistrationTests(TestCase):
    def test_registration_stores_first_and_last_name_separately(self):
        program = Program.objects.create(code='BSIT', name='Information Technology')
        response = self.client.post(reverse('accounts:register'), {
            'id_number': '2026-0123',
            'first_name': 'Maria Elena',
            'last_name': 'Dela Cruz',
            'year_level': '1st Year',
            'section': 'A',
            'program': str(program.pk),
            'password1': 'A-secure-password-123',
            'password2': 'A-secure-password-123',
        })

        self.assertRedirects(response, reverse('accounts:login'))
        user = get_user_model().objects.get(username='2026-0123')
        self.assertEqual(user.first_name, 'Maria Elena')
        self.assertEqual(user.last_name, 'Dela Cruz')
        self.assertEqual(user.get_full_name(), 'Maria Elena Dela Cruz')
        self.assertEqual(user.student_profile.id_number, '2026-0123')
        self.assertEqual(user.student_profile.program, program)
        self.assertEqual(user.student_profile.course, 'BSIT')
        self.assertFalse(hasattr(StudentProfile, 'full_name'))
