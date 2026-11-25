from django.db import models
from django.conf import settings
from portal.models import Course, Batch

User = settings.AUTH_USER_MODEL

class Question(models.Model):
    QUESTION_TYPES = (
        ('MCQ_SINGLE', 'Single Correct MCQ'),
        ('MCQ_MULTI', 'Multiple Select MCQ'),
        ('THEORY', 'Theory Question'),
        ('CODING', 'Coding Problem'),
        ('PRACTICAL', 'Practical Task'),
    )
    DIFFICULTY_LEVELS = (
        ('EASY', 'Easy'),
        ('MEDIUM', 'Medium'),
        ('HARD', 'Hard'),
    )

    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES, default='MCQ_SINGLE')
    course = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True, blank=True, related_name='questions')
    topic = models.CharField(max_length=150, blank=True, default='General')
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_LEVELS, default='MEDIUM')
    question_text = models.TextField()
    marks = models.PositiveIntegerField(default=1)
    explanation = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    is_approved = models.BooleanField(default=True, help_text="False for raw PDF-extracted questions awaiting trainer approval")
    created_at = models.DateTimeField(auto_now_add=True)

    # Theory specific fields
    keywords = models.TextField(blank=True, help_text="Comma-separated keywords required in student's answer sentence")

    # Coding specific fields
    input_format = models.TextField(blank=True)
    output_format = models.TextField(blank=True)
    constraints = models.TextField(blank=True)
    sample_input = models.TextField(blank=True)
    sample_output = models.TextField(blank=True)
    hidden_input = models.TextField(blank=True)
    hidden_output = models.TextField(blank=True)
    allowed_languages = models.CharField(max_length=100, default='python')

    # Practical specific fields
    submission_format = models.CharField(max_length=100, blank=True, default='.zip, .pdf, .docx')
    evaluation_criteria = models.TextField(blank=True)

    # Source PDF import tracking
    pdf_import = models.ForeignKey('PDFQuestionImport', on_delete=models.SET_NULL, null=True, blank=True, related_name='questions')
    pdf_name = models.CharField(max_length=255, blank=True, default='', help_text="Original PDF name if imported from PDF")

    class Meta:
        db_table = 'portal_questions'
        ordering = ['id']

    def __str__(self):
        return f"[{self.get_question_type_display()}] {self.question_text[:60]}"

    def get_sample_test_cases(self):
        """Return list of dicts [{'input': ..., 'output': ...}] for multiple sample test cases."""
        inps = [p.strip() for p in (self.sample_input or '').split('---') if p.strip()]
        outs = [p.strip() for p in (self.sample_output or '').split('---') if p.strip()]
        count = max(len(inps), len(outs), 1)
        cases = []
        for i in range(count):
            cases.append({
                'input': inps[i] if i < len(inps) else '',
                'output': outs[i] if i < len(outs) else ''
            })
        return cases

    def get_hidden_test_cases(self):
        """Return list of dicts [{'input': ..., 'output': ...}] for multiple hidden test cases."""
        inps = [p.strip() for p in (self.hidden_input or '').split('---') if p.strip()]
        outs = [p.strip() for p in (self.hidden_output or '').split('---') if p.strip()]
        count = max(len(inps), len(outs), 1)
        cases = []
        for i in range(count):
            cases.append({
                'input': inps[i] if i < len(inps) else '',
                'output': outs[i] if i < len(outs) else ''
            })
        return cases


class QuestionOption(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='options')
    option_letter = models.CharField(max_length=2)  # A, B, C, D
    option_text = models.TextField()
    is_correct = models.BooleanField(default=False)

    class Meta:
        db_table = 'portal_question_options'
        ordering = ['option_letter']

    def __str__(self):
        return f"{self.option_letter}. {self.option_text[:40]}"


class PDFQuestionImport(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending Extraction'),
        ('EXTRACTED', 'Extracted - Awaiting Approval'),
        ('APPROVED', 'Approved & Saved'),
        ('FAILED', 'Extraction Failed'),
    )
    trainer = models.ForeignKey(User, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True, blank=True, related_name='pdf_imports')
    pdf_name = models.CharField(max_length=255, blank=True, default='')
    pdf_file = models.FileField(upload_to='pdf_imports/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    extracted_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = 'portal_pdf_imports'
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"PDF Import #{self.id} ({self.pdf_name or self.pdf_file.name}) by {self.trainer.username} ({self.status})"


class Exam(models.Model):
    EXAM_TYPES = (
        ('MCQ', 'MCQ Examination'),
        ('CODING', 'Coding Examination'),
        ('PRACTICAL', 'Practical Examination'),
    )
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('SCHEDULED', 'Scheduled'),
        ('PUBLISHED', 'Published / Live'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    )

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='exams')
    batch = models.ForeignKey(Batch, on_delete=models.SET_NULL, null=True, blank=True, related_name='exams')
    exam_type = models.CharField(max_length=20, choices=EXAM_TYPES, default='MCQ')
    duration_minutes = models.PositiveIntegerField(default=60)
    total_marks = models.PositiveIntegerField(default=100)
    pass_marks = models.PositiveIntegerField(default=40)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_exams')
    is_proctored = models.BooleanField(default=True)
    shuffle_questions = models.BooleanField(default=False)
    shuffle_options = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    questions = models.ManyToManyField(Question, through='ExamQuestion', related_name='exams')

    class Meta:
        db_table = 'portal_exams'
        ordering = ['-start_time']

    def __str__(self):
        return f"{self.title} ({self.get_exam_type_display()})"


class ExamQuestion(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=1)
    marks = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = 'portal_exam_questions'
        ordering = ['order', 'id']
        unique_together = ('exam', 'question')


class ExamAssignment(models.Model):
    STATUS_CHOICES = (
        ('ASSIGNED', 'Assigned'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('MISSED', 'Missed'),
    )
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='assignments')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='exam_assignments')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ASSIGNED')
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'portal_exam_assignments'
        unique_together = ('exam', 'student')

    def __str__(self):
        return f"{self.exam.title} -> {self.student.username}"


class ExamSession(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='sessions')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='exam_sessions')
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    is_submitted = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    tab_switch_count = models.PositiveIntegerField(default=0)
    face_absence_count = models.PositiveIntegerField(default=0)
    multi_face_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'portal_exam_sessions'
        ordering = ['-start_time']

    def __str__(self):
        return f"Session: {self.exam.title} - {self.student.username}"


class StudentAnswer(models.Model):
    session = models.ForeignKey(ExamSession, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_option_letter = models.CharField(max_length=5, blank=True)  # 'A', 'B', etc.
    theory_answer = models.TextField(blank=True)
    submitted_code = models.TextField(blank=True)
    practical_file = models.FileField(upload_to='submissions/practical/', blank=True, null=True)
    is_marked_for_review = models.BooleanField(default=False)
    marks_obtained = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    is_evaluated = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'portal_student_answers'
        unique_together = ('session', 'question')


class ProctoringEvent(models.Model):
    EVENT_TYPES = (
        ('TAB_SWITCH', 'Browser Tab Switch'),
        ('FULLSCREEN_EXIT', 'Fullscreen Window Exited'),
        ('FACE_ABSENT', 'No Face Detected'),
        ('MULTIPLE_FACES', 'Multiple Faces Detected'),
        ('WEBCAM_DISCONNECTED', 'Webcam Permission Revoked'),
    )
    SEVERITY_LEVELS = (
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
    )
    session = models.ForeignKey(ExamSession, on_delete=models.CASCADE, related_name='proctoring_events')
    event_type = models.CharField(max_length=30, choices=EVENT_TYPES)
    severity = models.CharField(max_length=10, choices=SEVERITY_LEVELS, default='MEDIUM')
    details = models.CharField(max_length=255, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    is_reviewed = models.BooleanField(default=False)

    class Meta:
        db_table = 'portal_proctoring_events'
        ordering = ['-timestamp']

    def __str__(self):
        return f"[{self.severity}] {self.get_event_type_display()} ({self.session.student.username})"


class Result(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='results')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='exam_results')
    session = models.OneToOneField(ExamSession, on_delete=models.SET_NULL, null=True, blank=True)
    total_questions = models.PositiveIntegerField(default=0)
    correct_answers = models.PositiveIntegerField(default=0)
    wrong_answers = models.PositiveIntegerField(default=0)
    score = models.DecimalField(max_digits=6, decimal_places=2, default=0.0)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    is_passed = models.BooleanField(default=False)
    is_published = models.BooleanField(default=False)
    answers_approved = models.BooleanField(default=False, help_text="Trainer approved candidate to view question answers")
    trainer_feedback = models.TextField(blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'portal_results'
        unique_together = ('exam', 'student')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.student.username} - {self.exam.title}: {self.score}/{self.exam.total_marks}"


class ExamRetakeRequest(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending Admin Approval'),
        ('APPROVED', 'Approved by Admin'),
        ('REJECTED', 'Rejected'),
    )
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='retake_requests')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='retake_requests')
    reason = models.TextField(help_text="Reason for requesting retake")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    admin_notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_retakes')
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'portal_exam_retake_requests'
        ordering = ['-created_at']

    def __str__(self):
        return f"Retake Request: {self.student.username} for {self.exam.title} ({self.status})"
