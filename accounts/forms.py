from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import Program, User, StudentProfile, YEAR_LEVEL_CHOICES, SECTION_CHOICES


class StudentRegistrationForm(UserCreationForm):
    """Registration form for students.

    The student's ID Number is used as their username for login.
    """
    id_number = forms.CharField(label="ID Number", max_length=30)
    first_name = forms.CharField(label="First Name", max_length=150)
    last_name = forms.CharField(label="Last Name", max_length=150)
    year_level = forms.ChoiceField(
        label="Year",
        choices=YEAR_LEVEL_CHOICES,
    )
    section = forms.ChoiceField(label="Section", choices=SECTION_CHOICES)
    program = forms.ModelChoiceField(
        label="Program / Course",
        queryset=Program.objects.none(),
        empty_label="Select your program",
    )

    class Meta:
        model = User
        fields = (
            'id_number', 'first_name', 'last_name', 'year_level', 'section',
            'program', 'password1', 'password2',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['program'].queryset = Program.objects.filter(is_active=True)

    def clean_id_number(self):
        id_number = self.cleaned_data['id_number'].strip()
        if StudentProfile.objects.filter(id_number=id_number).exists():
            raise forms.ValidationError("This ID Number is already registered.")
        if User.objects.filter(username=id_number).exists():
            raise forms.ValidationError("This ID Number is already registered.")
        return id_number

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data['first_name'].strip()
        user.last_name = self.cleaned_data['last_name'].strip()
        user.username = self.cleaned_data['id_number']
        user.role = User.STUDENT
        if commit:
            user.save()
            StudentProfile.objects.create(
                user=user,
                id_number=self.cleaned_data['id_number'],
                year_level=self.cleaned_data['year_level'],
                section=self.cleaned_data['section'],
                program=self.cleaned_data['program'],
                course=self.cleaned_data['program'].code,
            )
        return user


class IDNumberAuthenticationForm(AuthenticationForm):
    """Allows students to log in using their ID Number, and instructors
    to log in using their instructor username. The widget label is
    generic so it works naturally for both roles."""
    username = forms.CharField(label="ID Number / Username")

