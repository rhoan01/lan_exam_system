from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView

from .forms import StudentRegistrationForm, IDNumberAuthenticationForm


class StudentRegisterView(CreateView):
    form_class = StudentRegistrationForm
    template_name = 'accounts/register.html'
    success_url = reverse_lazy('accounts:login')

    def form_valid(self, form):
        # form.clean_id_number() already checks for an existing ID Number,
        # but under concurrent requests (e.g. a double-click submit, or two
        # requests for the same ID arriving close together) two submissions
        # can both pass that check before either one actually saves. The
        # database's own UNIQUE constraint is the final safety net for that
        # race - catch it here so the student sees a normal form error
        # instead of a raw server crash.
        try:
            with transaction.atomic():
                response = super().form_valid(form)
            return response
        except IntegrityError:
            form.add_error(
                'id_number',
                "This ID Number was just registered (possibly by a duplicate submission). "
                "Please log in instead, or contact your instructor if this wasn't you."
            )
            return self.form_invalid(form)


class RoleAwareLoginView(LoginView):
    template_name = 'accounts/login.html'
    authentication_form = IDNumberAuthenticationForm


@login_required
def redirect_after_login(request):
    user = request.user
    if user.is_instructor():
        return redirect('exams:instructor_dashboard')
    return redirect('results:student_dashboard')
