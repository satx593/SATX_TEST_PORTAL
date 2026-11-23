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