from django.urls import path
from . import views

urlpatterns = [
    # Trainer URLs
    path('trainer/dashboard/', views.trainer_dashboard, name='trainer_dashboard'),
    path('trainer/question-bank/', views.question_bank, name='question_bank'),
    path('trainer/pdf-import/', views.pdf_import, name='pdf_import'),
    path('trainer/pdf-review/<int:import_id>/', views.pdf_review, name='pdf_review'),
    path('trainer/create-exam/', views.create_exam, name='create_exam'),
    path('trainer/monitoring/', views.live_monitoring, name='live_monitoring'),

    # Student URLs
    path('student/dashboard/', views.student_dashboard, name='student_dashboard'),
    path('student/exam/<int:exam_id>/instructions/', views.exam_instructions, name='exam_instructions'),
    path('student/exam/<int:exam_id>/room/', views.take_exam, name='take_exam'),
    path('student/exam/submit/<int:session_id>/', views.submit_exam, name='submit_exam'),
    path('student/results/', views.student_results, name='student_results'),

    # APIs for Exam Room
    path('api/save-answer/', views.save_answer_api, name='save_answer_api'),
    path('api/log-proctoring/', views.proctoring_event_api, name='proctoring_event_api'),
]
