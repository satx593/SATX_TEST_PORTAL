from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):

    def create_user(
        self,
        username,
        email=None,
        password=None,
        role='STUDENT',
        **extra_fields
    ):
        if not username:
            raise ValueError('The Username field must be set')

        email = self.normalize_email(email) if email else ''

        user = self.model(
            username=username,
            email=email,
            role=role,
            **extra_fields
        )

        user.set_password(password)
        user.save(using=self._db)

        return user

    def create_superuser(
        self,
        username,
        email=None,
        password=None,
        **extra_fields
    ):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'SUPER_ADMIN')

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')

        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(
            username=username,
            email=email,
            password=password,
            **extra_fields
        )


class User(AbstractUser):

    ROLE_CHOICES = (
        ('SUPER_ADMIN', 'Super Admin'),
        ('TRAINER', 'Trainer'),
        ('STUDENT', 'Student'),
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='STUDENT',
        db_index=True
    )

    phone_number = models.CharField(
        max_length=15,
        blank=True,
        null=True
    )

    # Profile pictures will be stored in Cloudinary
    profile_picture = models.ImageField(
        upload_to='profiles/',
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    class Meta:
        db_table = 'portal_users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    @property
    def is_super_admin(self):
        return self.role == 'SUPER_ADMIN' or self.is_superuser

    @property
    def is_trainer(self):
        return self.role == 'TRAINER'

    @property
    def is_student(self):
        return self.role == 'STUDENT'

    @property
    def display_name(self):
        if self.first_name or self.last_name:
            return f"{self.first_name} {self.last_name}".strip()

        return self.username

    def get_handled_courses(self):
        """
        Returns QuerySet of Course objects handled by this user:
        - Super Admin: All active courses
        - Trainer: Courses assigned directly to the trainer or via assigned batches
        - Student: The course the student is currently enrolled in
        """
        from portal.models import Course
        if self.is_super_admin:
            return Course.objects.all()
        if self.is_trainer:
            return Course.objects.filter(
                models.Q(trainers=self) |
                models.Q(batches__trainer=self) |
                models.Q(batches__trainers=self)
            ).distinct()
        if self.is_student:
            profile = getattr(self, 'student_profile', None)
            if profile and profile.course:
                return Course.objects.filter(id=profile.course_id)
        return Course.objects.none()

    def get_handled_batches(self):
        """
        Returns QuerySet of Batch objects handled by this user:
        - Super Admin: All batches
        - Trainer: Batches assigned directly or belonging to handled courses
        - Student: The batch the student is enrolled in
        """
        from portal.models import Batch
        if self.is_super_admin:
            return Batch.objects.all()
        if self.is_trainer:
            courses = self.get_handled_courses()
            return Batch.objects.filter(
                models.Q(course__in=courses) |
                models.Q(trainer=self) |
                models.Q(trainers=self)
            ).distinct()
        if self.is_student:
            profile = getattr(self, 'student_profile', None)
            if profile and profile.batch:
                return Batch.objects.filter(id=profile.batch_id)
        return Batch.objects.none()

    def get_visible_students(self):
        """
        Returns QuerySet of User objects (role='STUDENT'):
        - Super Admin: All students
        - Trainer: Only students enrolled in the trainer's handled courses or batches
        - Student: None (or self)
        """
        if self.is_super_admin:
            return User.objects.filter(role='STUDENT')
        if self.is_trainer:
            courses = self.get_handled_courses()
            batches = self.get_handled_batches()
            return User.objects.filter(role='STUDENT').filter(
                models.Q(student_profile__course__in=courses) |
                models.Q(student_profile__batch__in=batches)
            ).distinct()
        return User.objects.none()

    def get_visible_exams(self):
        """
        Returns QuerySet of Exam objects:
        - Super Admin: All exams
        - Trainer: Exams belonging to trainer's handled courses or created by this trainer
        - Student: Exams for student's course (and batch)
        """
        from exams.models import Exam
        if self.is_super_admin:
            return Exam.objects.all()
        if self.is_trainer:
            courses = self.get_handled_courses()
            return Exam.objects.filter(
                models.Q(course__in=courses) |
                models.Q(created_by=self)
            ).distinct()
        if self.is_student:
            profile = getattr(self, 'student_profile', None)
            if profile and profile.course:
                qs = Exam.objects.filter(course=profile.course, status__in=['PUBLISHED', 'SCHEDULED', 'COMPLETED'])
                if profile.batch:
                    qs = qs.filter(models.Q(batch=profile.batch) | models.Q(batch__isnull=True))
                return qs
        return Exam.objects.none()

    def get_visible_questions(self):
        """
        Returns QuerySet of Question objects:
        - Super Admin: All questions
        - Trainer: Questions belonging to trainer's handled courses or created by this trainer
        - Student: None (students do not browse question bank)
        """
        from exams.models import Question
        if self.is_super_admin:
            return Question.objects.all()
        if self.is_trainer:
            courses = self.get_handled_courses()
            return Question.objects.filter(
                models.Q(course__in=courses) |
                models.Q(created_by=self)
            ).distinct()
        return Question.objects.none()