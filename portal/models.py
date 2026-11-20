from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL

class Course(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    trainers = models.ManyToManyField(User, blank=True, related_name='assigned_courses')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'portal_courses'
        ordering = ['name']

    def __str__(self):
        return f"{self.code} - {self.name}"

    def get_trainers(self):
        return self.trainers.filter(is_active=True)

    def get_trainers_display(self):
        trs = self.get_trainers()
        if not trs.exists():
            return "Unassigned"
        return ", ".join([t.get_full_name() or t.username for t in trs])


class Batch(models.Model):
    name = models.CharField(max_length=100)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='batches')
    trainer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_batches')
    trainers = models.ManyToManyField(User, blank=True, related_name='assigned_batches_m2m')
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'portal_batches'
        verbose_name_plural = 'Batches'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.course.code})"

    def get_all_trainers(self):
        """Returns distinct list of trainers assigned to this batch."""
        trs = list(self.trainers.filter(is_active=True))
        if self.trainer and self.trainer.is_active and self.trainer not in trs:
            trs.insert(0, self.trainer)
        return trs

    def get_trainers_display(self):
        trs = self.get_all_trainers()
        if not trs:
            return "Unassigned"
        return ", ".join([t.get_full_name() or t.username for t in trs])


class TrainerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='trainer_profile')
    employee_id = models.CharField(max_length=50, unique=True)
    specialization = models.CharField(max_length=150, blank=True)
    department = models.CharField(max_length=100, default='Technical Training')

    class Meta:
        db_table = 'portal_trainer_profiles'

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} [{self.employee_id}]"


class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    reg_no = models.CharField(max_length=50, unique=True)
    course = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True, blank=True, related_name='students')
    batch = models.ForeignKey(Batch, on_delete=models.SET_NULL, null=True, blank=True, related_name='students')
    resume = models.FileField(upload_to='resumes/', blank=True, null=True)
    bio = models.TextField(blank=True)
    github_profile = models.URLField(blank=True, null=True)
    linkedin_profile = models.URLField(blank=True, null=True)

    class Meta:
        db_table = 'portal_student_profiles'

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.reg_no})"


class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=100)
    details = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'portal_audit_logs'
        ordering = ['-timestamp']

    def __str__(self):
        username = self.user.username if self.user else "System"
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M')}] {username} - {self.action}"
