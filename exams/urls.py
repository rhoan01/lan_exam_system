from django.urls import path
from . import views

app_name = 'exams'

urlpatterns = [
    path('', views.instructor_dashboard, name='instructor_dashboard'),
    path('subjects/create/', views.subject_create, name='subject_create'),
    path('subjects/<int:subject_id>/', views.subject_detail, name='subject_detail'),
    path('subjects/<int:subject_id>/delete/', views.subject_delete, name='subject_delete'),
    path('subjects/<int:subject_id>/delete/confirm/', views.subject_delete_confirm, name='subject_delete_confirm'),
    path('subjects/<int:subject_id>/exams/create/', views.exam_create, name='exam_create'),
    path('exams/<int:exam_id>/edit/', views.exam_edit, name='exam_edit'),
    path('exams/<int:exam_id>/', views.exam_detail, name='exam_detail'),
    path('exams/<int:exam_id>/publish/', views.exam_toggle_publish, name='exam_toggle_publish'),
    path('exams/<int:exam_id>/access/', views.exam_access_control, name='exam_access_control'),
    path('exams/<int:exam_id>/delete/', views.exam_delete, name='exam_delete'),
    path('exams/<int:exam_id>/questions/add/', views.question_create, name='question_create'),
    path('exams/<int:exam_id>/questions/import/', views.bulk_import_questions, name='bulk_import_questions'),
    path('exams/<int:exam_id>/results/', views.exam_results, name='exam_results'),
    path('exams/<int:exam_id>/results/export/', views.export_exam_results_csv, name='export_exam_results_csv'),
    path('exams/<int:exam_id>/results/export/pdf/', views.export_exam_results_pdf, name='export_exam_results_pdf'),
    path('questions/<int:question_id>/delete/', views.question_delete, name='question_delete'),
    path('questions/<int:question_id>/edit/', views.question_edit, name='question_edit'),
    path('attempts/<int:attempt_id>/reopen/', views.reopen_attempt, name='reopen_attempt'),
    path('attempts/<int:attempt_id>/grant-time/', views.grant_extra_time, name='grant_extra_time'),
    path('attempts/<int:attempt_id>/delete/', views.delete_in_progress_attempt, name='delete_in_progress_attempt'),
    path('attempts/<int:attempt_id>/view/', views.view_student_attempt, name='view_student_attempt'),
]
