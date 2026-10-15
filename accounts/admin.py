from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, StudentProfile


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'first_name', 'last_name', 'role', 'is_superuser')
    fieldsets = UserAdmin.fieldsets + (
        ('Role', {'fields': ('role',)}),
    )


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ('id_number', 'full_name', 'course', 'year_level', 'section')
    search_fields = ('id_number', 'full_name')
