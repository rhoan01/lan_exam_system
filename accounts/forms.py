from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import User, StudentProfile, YEAR_LEVEL_CHOICES, SECTION_CHOICES


class StudentRegistrationForm(UserCreationForm):
    """Registration form for students.

    The student's ID Number is used as their username for login.
    """
    id_number = forms.CharField(label="ID Number", max_length=30)
    full_name = forms.CharField(label="Full Name", max_length=150)
    year_level = forms.ChoiceField(
        label="Year",
        choices=YEAR_LEVEL_CHOICES,
    )
    section = forms.ChoiceField(label="Section", choices=SECTION_CHOICES)
    course = forms.CharField(label="Course", max_length=100)

    class Meta:
        model = User
        fields = ('id_number', 'full_name', 'year_level', 'section', 'course', 'password1', 'password2')

    def clean_id_number(self):
        id_number = self.cleaned_data['id_number'].strip()
        if StudentProfile.objects.filter(id_number=id_number).exists():
            raise forms.ValidationError("This ID Number is already registered.")
        if User.objects.filter(username=id_number).exists():
            raise forms.ValidationError("This ID Number is already registered.")
        return id_number

    def save(self, commit=True):
        user = super().save(commit=False)
        full_name = self.cleaned_data['full_name'].strip()
        name_parts = full_name.split(' ', 1)
        user.first_name = name_parts[0]
        user.last_name = name_parts[1] if len(name_parts) > 1 else ''
        user.username = self.cleaned_data['id_number']
        user.role = User.STUDENT
        if commit:
            user.save()
            StudentProfile.objects.create(
                user=user,
                id_number=self.cleaned_data['id_number'],
                full_name=full_name,
                year_level=self.cleaned_data['year_level'],
                section=self.cleaned_data['section'],
                course=self.cleaned_data['course'],
            )
        return user


class IDNumberAuthenticationForm(AuthenticationForm):
    """Allows students to log in using their ID Number, and instructors
    to log in using their instructor username. The widget label is
    generic so it works naturally for both roles."""
    username = forms.CharField(label="ID Number / Username")

