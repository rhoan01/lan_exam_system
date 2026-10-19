from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Program, User, StudentProfile


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('code', 'name')


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'first_name', 'last_name', 'role', 'is_superuser')
    fieldsets = UserAdmin.fieldsets + (
        ('Role', {'fields': ('role',)}),
    )


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ('id_number', 'student_name', 'program', 'year_level', 'section')
    search_fields = ('id_number', 'user__first_name', 'user__last_name')
    list_select_related = ('user', 'program')

    @admin.display(description='Student name', ordering='user__last_name')
    def student_name(self, profile):
        return profile.user.get_full_name() or profile.user.username
