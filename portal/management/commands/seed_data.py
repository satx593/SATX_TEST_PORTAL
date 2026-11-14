from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from accounts.models import User
from portal.models import Course, Batch, TrainerProfile, StudentProfile, AuditLog
from exams.models import Question, QuestionOption, Exam, ExamQuestion, ExamAssignment

class Command(BaseCommand):
    help = 'Seeds initial demo accounts, course, batch, questions, and a published exam.'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.NOTICE('Seeding PUMO Technovation Exam Portal initial data...'))

        # 1. Super Admin
        admin, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@pumotechnovation.com',
                'first_name': 'Super',
                'last_name': 'Admin',
                'role': 'SUPER_ADMIN',
                'is_staff': True,
                'is_superuser': True,
            }
        )
        admin.set_password('Sarathy@123')
        admin.role = 'SUPER_ADMIN'
        admin.is_staff = True
        admin.is_superuser = True
        admin.save()
        self.stdout.write(self.style.SUCCESS(f"Super Admin ready: admin / Sarathy@123"))

        # 2. Demo Course
        course, _ = Course.objects.get_or_create(
            code='PY-FS-01',
            defaults={
                'name': 'Python Full Stack Development',
                'description': 'Comprehensive training in Python, Django, MySQL, REST APIs, and modern frontend technologies.',
                'is_active': True
            }
        )

        # 3. Demo Trainer
        trainer, _ = User.objects.get_or_create(
            username='trainer',
            defaults={
                'email': 'trainer@pumotechnovation.com',
                'first_name': 'Karthik',
                'last_name': 'Rajan',
                'role': 'TRAINER',
            }
        )
        trainer.set_password('Trainer@123')
        trainer.role = 'TRAINER'
        trainer.save()
        TrainerProfile.objects.get_or_create(
            user=trainer,
            defaults={
                'employee_id': 'PUMO-TR-01',
                'specialization': 'Python & Django Architecture',
                'department': 'Technical Training - Poonamallee'
            }
        )
        self.stdout.write(self.style.SUCCESS(f"Trainer ready: trainer / Trainer@123"))

        # 4. Demo Batch
        batch, _ = Batch.objects.get_or_create(
            name='Batch 2026-A (Poonamallee)',
            course=course,
            defaults={
                'trainer': trainer,
                'start_date': timezone.now().date(),
                'end_date': (timezone.now() + timedelta(days=90)).date(),
                'is_active': True
            }
        )

        # 5. Demo Student
        student, _ = User.objects.get_or_create(
            username='student',
            defaults={
                'email': 'student@pumotechnovation.com',
                'first_name': 'Praveen',
                'last_name': 'Kumar',
                'role': 'STUDENT',
            }
        )
        student.set_password('Student@123')
        student.role = 'STUDENT'
        student.save()
        StudentProfile.objects.get_or_create(
            user=student,
            defaults={
                'reg_no': 'PUMO2026001',
                'course': course,
                'batch': batch
            }
        )
        self.stdout.write(self.style.SUCCESS(f"Student ready: student / Student@123"))

        # 6. Sample Questions
        sample_mcqs = [
            {
                'text': 'Which of the following is an immutable sequence data type in Python?',
                'topic': 'Python Basics',
                'difficulty': 'EASY',
                'explanation': 'Tuples are immutable sequences in Python; their elements cannot be modified after assignment.',
                'options': [
                    ('A', 'list', False),
                    ('B', 'tuple', True),
                    ('C', 'set', False),
                    ('D', 'dict', False),
                ]
            },
            {
                'text': 'In Django ORM, which method retrieves a single record and raises DoesNotExist if not found?',
                'topic': 'Django Models',
                'difficulty': 'EASY',
                'explanation': 'Model.objects.get() returns exactly one matching model instance or raises DoesNotExist.',
                'options': [
                    ('A', 'filter()', False),
                    ('B', 'first()', False),
                    ('C', 'get()', True),
                    ('D', 'all()', False),
                ]
            },
            {
                'text': 'What is the default port number used by MySQL Community Server?',
                'topic': 'Database',
                'difficulty': 'EASY',
                'explanation': 'MySQL servers by default listen for incoming TCP connections on port 3306.',
                'options': [
                    ('A', '5432', False),
                    ('B', '3306', True),
                    ('C', '27017', False),
                    ('D', '8080', False),
                ]
            },
            {
                'text': 'Which Django template tag is required inside every POST form to protect against CSRF attacks?',
                'topic': 'Django Security',
                'difficulty': 'MEDIUM',
                'explanation': '{% csrf_token %} generates a hidden input with the CSRF token needed for validation.',
                'options': [
                    ('A', '{% csrf_token %}', True),
                    ('B', '{% safe %}', False),
                    ('C', '{% security_token %}', False),
                    ('D', '{% auth_check %}', False),
                ]
            },
            {
                'text': 'Which Python library allows high-performance PDF rendering, text extraction, and OCR support?',
                'topic': 'PDF Processing',
                'difficulty': 'MEDIUM',
                'explanation': 'PyMuPDF (fitz) provides fast, multi-page PDF text and block extraction.',
                'options': [
                    ('A', 'PyMuPDF (fitz)', True),
                    ('B', 'Flask', False),
                    ('C', 'NLTK', False),
                    ('D', 'Celery', False),
                ]
            },
        ]

        created_questions = []
        for q_data in sample_mcqs:
            q, _ = Question.objects.get_or_create(
                question_text=q_data['text'],
                defaults={
                    'question_type': 'MCQ_SINGLE',
                    'course': course,
                    'topic': q_data['topic'],
                    'difficulty': q_data['difficulty'],
                    'marks': 10,
                    'explanation': q_data['explanation'],
                    'created_by': trainer,
                    'is_approved': True
                }
            )
            # Recreate or ensure options
            if not q.options.exists():
                for letter, text, is_corr in q_data['options']:
                    QuestionOption.objects.create(
                        question=q,
                        option_letter=letter,
                        option_text=text,
                        is_correct=is_corr
                    )
            created_questions.append(q)

        # 7. Create Sample Published Exam
        start_now = timezone.now() - timedelta(minutes=5)
        end_later = timezone.now() + timedelta(days=7)

        exam, _ = Exam.objects.get_or_create(
            title='Python & Django Full-Stack Certification Exam',
            defaults={
                'description': 'Official assessment for PUMO Technovation Poonamallee batch covering Python, Django ORM, MySQL and Security.',
                'course': course,
                'batch': batch,
                'exam_type': 'MCQ',
                'duration_minutes': 30,
                'total_marks': 50,
                'pass_marks': 25,
                'start_time': start_now,
                'end_time': end_later,
                'status': 'PUBLISHED',
                'created_by': trainer,
                'is_proctored': True,
                'shuffle_questions': False,
                'shuffle_options': False
            }
        )

        # Attach questions
        for idx, q in enumerate(created_questions, start=1):
            ExamQuestion.objects.get_or_create(
                exam=exam,
                question=q,
                defaults={'order': idx, 'marks': 10}
            )

        # Assign to demo student
        ExamAssignment.objects.get_or_create(
            exam=exam,
            student=student,
            defaults={'status': 'ASSIGNED'}
        )

        # 8. Audit log
        AuditLog.objects.create(
            user=admin,
            action='SEED_DATA_INITIALIZED',
            details='Initialized demo course, batch, trainer, student, and published certification exam.'
        )

        self.stdout.write(self.style.SUCCESS('Successfully seeded all initial demo accounts and examination data!'))
