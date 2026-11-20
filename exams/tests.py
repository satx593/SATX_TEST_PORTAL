import json
from decimal import Decimal
from datetime import timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model
from exams.models import Exam, ExamQuestion, Question, ExamSession, StudentAnswer, Result
from portal.models import Course, Batch, StudentProfile

User = get_user_model()

class TheoryAndExamFeaturesTestCase(TestCase):
    def setUp(self):
        self.trainer = User.objects.create_user(
            username='trainer1',
            email='trainer@example.com',
            password='password123',
            role='TRAINER'
        )
        self.admin = User.objects.create_user(
            username='admin1',
            email='admin@example.com',
            password='password123',
            role='SUPER_ADMIN'
        )
        self.student = User.objects.create_user(
            username='student1',
            email='student@example.com',
            password='password123',
            role='STUDENT'
        )
        self.course = Course.objects.create(name='Python Dev', code='PY101')
        self.batch = Batch.objects.create(name='Batch A', course=self.course)
        self.student_profile, _ = StudentProfile.objects.get_or_create(user=self.student)

    def test_theory_keyword_matching_auto_eval(self):
        # Create theory question with keywords
        q = Question.objects.create(
            created_by=self.trainer,
            question_type='THEORY',
            question_text='Explain what Python is.',
            keywords='interpreted, high-level, dynamic',
            marks=5
        )

        now = timezone.now()
        exam = Exam.objects.create(
            title='Python Test',
            created_by=self.trainer,
            duration_minutes=30,
            pass_marks=2,
            total_marks=5,
            course=self.course,
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=2),
            status='PUBLISHED'
        )
        eq = ExamQuestion.objects.create(exam=exam, question=q, marks=5, order=1)

        session = ExamSession.objects.create(exam=exam, student=self.student)

        client = Client()
        client.login(username='student1', password='password123')

        # Save theory answer via API
        save_url = reverse('save_answer_api')
        payload = {
            'session_id': session.id,
            'question_id': q.id,
            'theory_answer': 'Python is an interpreted programming language used worldwide.'
        }
        resp = client.post(save_url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(resp.status_code, 200)

        # Verify saved answer
        ans = StudentAnswer.objects.get(session=session, question=q)
        self.assertIn('interpreted', ans.theory_answer)

        # Submit exam
        submit_url = reverse('submit_exam', args=[session.id])
        resp = client.post(submit_url)
        self.assertEqual(resp.status_code, 302)

        ans.refresh_from_db()
        self.assertTrue(ans.is_evaluated)
        self.assertEqual(ans.marks_obtained, Decimal('5.00'))

        result = Result.objects.get(student=self.student, exam=exam)
        self.assertEqual(result.score, Decimal('5.00'))
        self.assertFalse(result.answers_approved)

    def test_admin_toggle_answers_approval(self):
        now = timezone.now()
        exam = Exam.objects.create(
            title='Mock Exam',
            created_by=self.trainer,
            duration_minutes=30,
            course=self.course,
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=2),
            status='COMPLETED'
        )
        result = Result.objects.create(
            student=self.student,
            exam=exam,
            score=10,
            percentage=100,
            answers_approved=False
        )

        client = Client()
        client.login(username='admin1', password='password123')

        toggle_url = reverse('admin_toggle_answers_approval', args=[result.id])
        resp = client.post(toggle_url, HTTP_REFERER='/portal/leaderboard/')
        self.assertEqual(resp.status_code, 302)

        result.refresh_from_db()
        self.assertTrue(result.answers_approved)

    def test_admin_student_edit(self):
        client = Client()
        client.login(username='admin1', password='password123')

        students_url = reverse('admin_students')
        resp = client.post(students_url, {
            'action': 'edit',
            'student_id': self.student.id,
            'first_name': 'UpdatedFirst',
            'last_name': 'UpdatedLast',
            'email': 'updated@example.com',
            'reg_no': 'REG999',
            'course': self.course.id,
            'batch': self.batch.id,
            'is_active': 'on'
        })
        self.assertEqual(resp.status_code, 302)

        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, 'UpdatedFirst')
        self.assertEqual(self.student.last_name, 'UpdatedLast')
        self.assertEqual(self.student.email, 'updated@example.com')

        self.student_profile.refresh_from_db()
        self.assertEqual(self.student_profile.reg_no, 'REG999')
        self.assertEqual(self.student_profile.course, self.course)
        self.assertEqual(self.student_profile.batch, self.batch)

    def test_download_qa_sheet_pdf(self):
        now = timezone.now()
        exam = Exam.objects.create(
            title='PDF Download Exam',
            created_by=self.trainer,
            duration_minutes=30,
            course=self.course,
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=2),
            status='COMPLETED'
        )
        session = ExamSession.objects.create(exam=exam, student=self.student, is_submitted=True)
        q = Question.objects.create(
            created_by=self.trainer,
            question_type='THEORY',
            question_text='What is Django?',
            keywords='framework',
            marks=2
        )
        ExamQuestion.objects.create(exam=exam, question=q, marks=2, order=1)
        StudentAnswer.objects.create(
            session=session,
            question=q,
            theory_answer='Django is a web framework.',
            marks_obtained=Decimal('2.00'),
            is_evaluated=True
        )
        result = Result.objects.create(
            student=self.student,
            exam=exam,
            session=session,
            score=2,
            percentage=100,
            answers_approved=False
        )

        client = Client()
        client.login(username='student1', password='password123')

        download_url = reverse('download_qa_sheet_pdf', args=[result.id])

        # 1. When not approved: student gets redirected
        resp = client.get(download_url)
        self.assertEqual(resp.status_code, 302)

        # 2. When approved: student can download PDF
        result.answers_approved = True
        result.save()

        resp = client.get(download_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertIn('attachment; filename=', resp['Content-Disposition'])

