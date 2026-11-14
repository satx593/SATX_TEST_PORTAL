from django.urls import path
from . import views

urlpatterns = [
    path('admin/dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin/trainers/', views.admin_trainers, name='admin_trainers'),
    path('admin/students/', views.admin_students, name='admin_students'),
    path('admin/courses/', views.admin_courses, name='admin_courses'),
    path('admin/batches/', views.admin_batches, name='admin_batches'),
    path('admin/audit-logs/', views.admin_audit_logs, name='admin_audit_logs'),
]
