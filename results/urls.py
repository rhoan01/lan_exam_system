from django.urls import path
from . import views

app_name = 'results'

urlpatterns = [
    path('', views.student_dashboard, name='student_dashboard'),
    path('redeem-access-code/', views.redeem_access_code, name='redeem_access_code'),
    path('exams/<int:exam_id>/take/', views.take_exam, name='take_exam'),
    path('exams/<int:exam_id>/autosave/', views.autosave_exam, name='autosave_exam'),
    path('exams/<int:exam_id>/submit/', views.submit_exam, name='submit_exam'),
    path('exams/<int:exam_id>/log-tab-switch/', views.log_tab_switch, name='log_tab_switch'),
    path('attempts/<int:attempt_id>/result/', views.attempt_result, name='attempt_result'),
]
