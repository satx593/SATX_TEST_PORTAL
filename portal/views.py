import csv
import io
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Avg, Count
from accounts.models import User
from accounts.decorators import admin_required
from portal.models import Course, Batch, TrainerProfile, StudentProfile, AuditLog
from exams.models import Exam, Result

@admin_required
def admin_dashboard(request):
    """Super Admin high-level metrics dashboard."""
    students_count = User.objects.filter(role='STUDENT').count()
    trainers_count = User.objects.filter(role='TRAINER').count()
    courses_count = Course.objects.count()
    batches_count = Batch.objects.count()
    exams_count = Exam.objects.count()
    active_exams_count = Exam.objects.filter(status='PUBLISHED').count()

    results = Result.objects.all()
    avg_score = results.aggregate(avg=Avg('percentage'))['avg'] or 0.0

    recent_audits = AuditLog.objects.select_related('user').all()[:8]
    recent_exams = Exam.objects.select_related('course', 'batch').all()[:5]

    context = {
        'students_count': students_count,
        'trainers_count': trainers_count,
        'courses_count': courses_count,
        'batches_count': batches_count,
        'exams_count': exams_count,
        'active_exams_count': active_exams_count,
        'avg_score': round(avg_score, 1),
        'recent_audits': recent_audits,
        'recent_exams': recent_exams,
    }
    return render(request, 'admin_portal/dashboard.html', context)


@admin_required
def admin_trainers(request):
    """Trainer account management."""
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create':
            username = request.POST.get('username', '').strip()
            email = request.POST.get('email', '').strip()
            password = request.POST.get('password', '').strip()
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            employee_id = request.POST.get('employee_id', '').strip()
            specialization = request.POST.get('specialization', '').strip()

            if User.objects.filter(username=username).exists():
                messages.error(request, f"Username '{username}' already exists.")
            elif TrainerProfile.objects.filter(employee_id=employee_id).exists():
                messages.error(request, f"Employee ID '{employee_id}' is already registered.")
            else:
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    role='TRAINER',
                    first_name=first_name,
                    last_name=last_name
                )
                TrainerProfile.objects.create(
                    user=user,
                    employee_id=employee_id,
                    specialization=specialization,
                    department='Technical Training'
                )
                AuditLog.objects.create(
                    user=request.user,
                    action='TRAINER_CREATED',
                    details=f"Created trainer {username} ({employee_id})"
                )
                messages.success(request, f"Trainer '{username}' created successfully.")
            return redirect('admin_trainers')

        elif action == 'toggle_status':
            trainer_id = request.POST.get('trainer_id')
            trainer_user = get_object_or_404(User, id=trainer_id, role='TRAINER')
            trainer_user.is_active = not trainer_user.is_active
            trainer_user.save()
            status_text = "activated" if trainer_user.is_active else "deactivated"
            messages.info(request, f"Trainer '{trainer_user.username}' has been {status_text}.")
            return redirect('admin_trainers')

    trainers = User.objects.filter(role='TRAINER').select_related('trainer_profile').order_by('-date_joined')
    return render(request, 'admin_portal/trainers.html', {'trainers': trainers})


@admin_required
def admin_students(request):
    """Student account management with search, filter, and bulk CSV upload."""
    courses = Course.objects.filter(is_active=True)
    batches = Batch.objects.filter(is_active=True)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create':
            username = request.POST.get('username', '').strip()
            email = request.POST.get('email', '').strip()
            password = request.POST.get('password', '').strip()
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            reg_no = request.POST.get('reg_no', '').strip()
            course_id = request.POST.get('course')
            batch_id = request.POST.get('batch')

            if User.objects.filter(username=username).exists():
                messages.error(request, f"Username '{username}' already exists.")
            elif StudentProfile.objects.filter(reg_no=reg_no).exists():
                messages.error(request, f"Registration No '{reg_no}' is already registered.")
            else:
                course = Course.objects.filter(id=course_id).first() if course_id else None
                batch = Batch.objects.filter(id=batch_id).first() if batch_id else None

                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    role='STUDENT',
                    first_name=first_name,
                    last_name=last_name
                )
                StudentProfile.objects.create(
                    user=user,
                    reg_no=reg_no,
                    course=course,
                    batch=batch
                )
                AuditLog.objects.create(
                    user=request.user,
                    action='STUDENT_CREATED',
                    details=f"Created student {username} ({reg_no})"
                )
                messages.success(request, f"Student '{username}' added successfully.")
            return redirect('admin_students')

        elif action == 'bulk_upload':
            csv_file = request.FILES.get('csv_file')
            if not csv_file or not csv_file.name.endswith('.csv'):
                messages.error(request, "Please upload a valid CSV file.")
                return redirect('admin_students')

            decoded_file = csv_file.read().decode('utf-8', errors='ignore')
            io_string = io.StringIO(decoded_file)
            reader = csv.DictReader(io_string)

            created_count = 0
            for row in reader:
                uname = row.get('username', '').strip()
                rno = row.get('reg_no', '').strip()
                pwd = row.get('password', 'Student@123').strip()
                fname = row.get('first_name', '').strip()
                lname = row.get('last_name', '').strip()
                email = row.get('email', '').strip()

                if uname and rno and not User.objects.filter(username=uname).exists():
                    u = User.objects.create_user(
                        username=uname,
                        email=email,
                        password=pwd,
                        role='STUDENT',
                        first_name=fname,
                        last_name=lname
                    )
                    StudentProfile.objects.create(user=u, reg_no=rno)
                    created_count += 1

            messages.success(request, f"Bulk import complete: {created_count} students created.")
            return redirect('admin_students')

    # Filtering
    query = request.GET.get('q', '').strip()
    batch_filter = request.GET.get('batch', '')

    students = User.objects.filter(role='STUDENT').select_related('student_profile', 'student_profile__batch', 'student_profile__course')
    if query:
        students = students.filter(username__icontains=query) | students.filter(first_name__icontains=query) | students.filter(student_profile__reg_no__icontains=query)
    if batch_filter:
        students = students.filter(student_profile__batch_id=batch_filter)

    return render(request, 'admin_portal/students.html', {
        'students': students.order_by('-date_joined'),
        'courses': courses,
        'batches': batches,
        'query': query,
        'batch_filter': batch_filter
    })


@admin_required
def admin_courses(request):
    """Course catalog view."""
    if request.method == 'POST':
        code = request.POST.get('code', '').strip().upper()
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()

        if Course.objects.filter(code=code).exists():
            messages.error(request, f"Course code '{code}' already exists.")
        else:
            Course.objects.create(code=code, name=name, description=description)
            messages.success(request, f"Course '{name}' added successfully.")
        return redirect('admin_courses')

    courses = Course.objects.annotate(batches_count=Count('batches')).order_by('name')
    return render(request, 'admin_portal/courses.html', {'courses': courses})


@admin_required
def admin_batches(request):
    """Batch management."""
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        course_id = request.POST.get('course')
        trainer_id = request.POST.get('trainer')
        start_date = request.POST.get('start_date') or None
        end_date = request.POST.get('end_date') or None

        course = get_object_or_404(Course, id=course_id)
        trainer = User.objects.filter(id=trainer_id, role='TRAINER').first() if trainer_id else None

        Batch.objects.create(
            name=name,
            course=course,
            trainer=trainer,
            start_date=start_date,
            end_date=end_date
        )
        messages.success(request, f"Batch '{name}' created successfully.")
        return redirect('admin_batches')

    batches = Batch.objects.select_related('course', 'trainer').annotate(students_count=Count('students')).order_by('-created_at')
    courses = Course.objects.filter(is_active=True)
    trainers = User.objects.filter(role='TRAINER', is_active=True)
    return render(request, 'admin_portal/batches.html', {
        'batches': batches,
        'courses': courses,
        'trainers': trainers
    })


@admin_required
def admin_audit_logs(request):
    """Audit trails of system activities."""
    logs = AuditLog.objects.select_related('user').all()[:100]
    return render(request, 'admin_portal/audit_logs.html', {'logs': logs})
