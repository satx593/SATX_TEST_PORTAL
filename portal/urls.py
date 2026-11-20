from django.urls import path
from . import views

urlpatterns = [
    path('admin/dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin/trainers/', views.admin_trainers, name='admin_trainers'),
    path('admin/students/', views.admin_students, name='admin_students'),
    path('trainer/students/', views.admin_students, name='trainer_students'),
    path('admin/courses/', views.admin_courses, name='admin_courses'),
    path('admin/batches/', views.admin_batches, name='admin_batches'),
    path('admin/audit-logs/', views.admin_audit_logs, name='admin_audit_logs'),
    path('admin/retake-requests/', views.admin_retakes, name='admin_retakes'),
    path('admin/leaderboard/', views.admin_leaderboard, name='admin_leaderboard'),
    path('admin/leaderboard/export-csv/', views.admin_export_results_csv, name='admin_export_results_csv'),
    path('admin/leaderboard/export-pdf/', views.admin_export_results_pdf, name='admin_export_results_pdf'),
    path('admin/leaderboard/student-report/<int:result_id>/', views.admin_student_single_report, name='admin_student_single_report'),
    path('admin/leaderboard/toggle-answers/<int:result_id>/', views.admin_toggle_answers_approval, name='admin_toggle_answers_approval'),
]
