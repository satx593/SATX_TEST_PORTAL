from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
import json

from accounts.models import User
from portal.models import Course, Batch, StudentProfile, TrainerProfile
from exams.models import Question, QuestionOption, Exam, ExamQuestion, ExamAssignment, ExamSession, StudentAnswer, Result

class PortalEndToEndIntegrationTests(TestCase):
    def setUp(self):
        self.client = Client()

        # 1. Admin
        self.admin = User.objects.create_superuser(
            username='admin_test',
            email='admin@test.com',
            password='Password123!',
            first_name='Admin',
            last_name='User'
        )

        # 2. Course & Batch
        self.course = Course.objects.create(
            code='TEST-01',
            name='Test Python Course',
            description='Test course description'
        )

        # 3. Trainer
        self.trainer = User.objects.create_user(
            username='trainer_test',
            email='trainer@test.com',
            password='Password123!',
            role='TRAINER',
            first_name='Trainer',
            last_name='User'
        )
        self.trainer_profile = TrainerProfile.objects.create(
            user=self.trainer,
            employee_id='TR-TEST-01'
        )

        self.batch = Batch.objects.create(
            name='Test Batch 1',
            course=self.course,
            trainer=self.trainer
        )

        # 4. Student
        self.student = User.objects.create_user(
            username='student_test',
            email='student@test.com',
            password='Password123!',
            role='STUDENT',
            first_name='Student',
            last_name='User'
        )
        self.student_profile = StudentProfile.objects.create(
            user=self.student,
            reg_no='REG-TEST-01',
            course=self.course,
            batch=self.batch
        )

        # 5. Question & Options
        self.question = Question.objects.create(
            question_type='MCQ_SINGLE',
            course=self.course,
            question_text='What is the output of len([1, 2, 3])?',
            marks=10,
            created_by=self.trainer,
            is_approved=True
        )
        self.opt_a = QuestionOption.objects.create(question=self.question, option_letter='A', option_text='2', is_correct=False)
        self.opt_b = QuestionOption.objects.create(question=self.question, option_letter='B', option_text='3', is_correct=True)
        self.opt_c = QuestionOption.objects.create(question=self.question, option_letter='C', option_text='4', is_correct=False)

        # 6. Exam
        now = timezone.now()
        self.exam = Exam.objects.create(
            title='Test Midterm Exam',
            course=self.course,
            batch=self.batch,
            exam_type='MCQ',
            duration_minutes=30,
            total_marks=10,
            pass_marks=5,
            start_time=now - timedelta(minutes=5),
            end_time=now + timedelta(days=1),
            status='PUBLISHED',
            created_by=self.trainer
        )
        ExamQuestion.objects.create(exam=self.exam, question=self.question, order=1, marks=10)
        ExamAssignment.objects.create(exam=self.exam, student=self.student)

    def test_login_and_role_based_redirection(self):
        """Test login workflow and redirection based on roles."""
        # Admin Login
        login_res = self.client.post(reverse('login'), {'username': 'admin_test', 'password': 'Password123!'})
        self.assertEqual(login_res.status_code, 302)
        self.assertEqual(login_res.url, reverse('dashboard_redirect'))
        redirect_res = self.client.get(reverse('dashboard_redirect'))
        self.assertRedirects(redirect_res, reverse('admin_dashboard'))

        self.client.logout()

        # Student Login
        student_res = self.client.post(reverse('login'), {'username': 'student_test', 'password': 'Password123!'})
        self.assertEqual(student_res.status_code, 302)
        self.assertEqual(student_res.url, reverse('dashboard_redirect'))
        redirect_res = self.client.get(reverse('dashboard_redirect'))
        self.assertRedirects(redirect_res, reverse('student_dashboard'))

    def test_strict_role_based_access_security(self):
        """Students must never be allowed to access admin or trainer views."""
        self.client.login(username='student_test', password='Password123!')

        # Student trying to access Super Admin dashboard
        res = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(res.status_code, 302)
        self.assertIn('/student/dashboard/', res.url)

        # Student trying to access Trainer dashboard
        res = self.client.get(reverse('trainer_dashboard'))
        self.assertEqual(res.status_code, 302)
        self.assertIn('/student/dashboard/', res.url)

    def test_student_examination_flow_and_auto_scoring(self):
        """Test full student exam journey: start exam, auto-save answer, submit, and verify score calculation."""
        self.client.login(username='student_test', password='Password123!')

        # 1. Access exam room
        room_res = self.client.get(reverse('take_exam', kwargs={'exam_id': self.exam.id}))
        self.assertEqual(room_res.status_code, 200)

        session = ExamSession.objects.get(exam=self.exam, student=self.student)

        # 2. Save answer via AJAX API
        save_res = self.client.post(
            reverse('save_answer_api'),
            data=json.dumps({
                'session_id': session.id,
                'question_id': self.question.id,
                'selected_option': 'B',
                'is_review': False
            }),
            content_type='application/json'
        )
        self.assertEqual(save_res.status_code, 200)
        self.assertEqual(save_res.json()['status'], 'success')

        answer = StudentAnswer.objects.get(session=session, question=self.question)
        self.assertEqual(answer.selected_option_letter, 'B')

        # 3. Submit exam
        submit_res = self.client.get(reverse('submit_exam', kwargs={'session_id': session.id}))
        self.assertRedirects(submit_res, reverse('student_results'))

        # 4. Verify evaluation & score
        result = Result.objects.get(exam=self.exam, student=self.student)
        self.assertEqual(result.score, Decimal('10.0'))
        self.assertEqual(result.percentage, Decimal('100.0'))
        self.assertTrue(result.is_passed)
        self.assertEqual(result.correct_answers, 1)

    def test_mandatory_branding_and_developer_credits(self):
        """Verify developer credits 'SARATHY & THIRUMAL' render properly in templates."""
        res = self.client.get(reverse('login'))
        self.assertContains(res, "PUMO TECHNOVATION")
        self.assertContains(res, "POONAMALLEE")
        self.assertContains(res, "Developed By <strong>SARATHY &amp; THIRUMAL</strong>")
        self.assertContains(res, "2026 PUMO TECHNOVATION. All Rights Reserved.")
