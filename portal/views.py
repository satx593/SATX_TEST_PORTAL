import csv
import io
import os
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Q
from django.utils import timezone
from django.conf import settings
from accounts.models import User
from accounts.decorators import admin_required, trainer_required
from accounts.emails import send_student_welcome_email, send_student_password_reset_email
from portal.models import Course, Batch, TrainerProfile, StudentProfile, AuditLog
from exams.models import Exam, Result, ExamRetakeRequest, ExamAssignment, ExamSession, StudentAnswer

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
    """Trainer account management — create, edit, toggle status, and delete."""
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
            course_ids = request.POST.getlist('courses') or request.POST.getlist('courses[]')

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
                if course_ids:
                    user.assigned_courses.set(course_ids)
                AuditLog.objects.create(
                    user=request.user,
                    action='TRAINER_CREATED',
                    details=f"Created trainer {username} ({employee_id}) with {len(course_ids)} assigned courses"
                )
                messages.success(request, f"Trainer '{username}' created successfully.")
            return redirect('admin_trainers')

        elif action == 'edit':
            trainer_id = request.POST.get('trainer_id')
            trainer_user = get_object_or_404(User, id=trainer_id, role='TRAINER')
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            email = request.POST.get('email', '').strip()
            employee_id = request.POST.get('employee_id', '').strip()
            specialization = request.POST.get('specialization', '').strip()
            department = request.POST.get('department', 'Technical Training').strip()
            new_password = request.POST.get('password', '').strip()
            is_active = request.POST.get('is_active') in ('on', 'true', '1', True, 'ACTIVE')
            course_ids = request.POST.getlist('courses') or request.POST.getlist('courses[]')

            if employee_id and TrainerProfile.objects.filter(employee_id=employee_id).exclude(user=trainer_user).exists():
                messages.error(request, f"Employee ID '{employee_id}' is already registered to another trainer.")
            else:
                trainer_user.first_name = first_name
                trainer_user.last_name = last_name
                trainer_user.email = email
                trainer_user.is_active = is_active
                if new_password:
                    trainer_user.set_password(new_password)
                trainer_user.save()
                trainer_user.assigned_courses.set(course_ids)

                profile, _ = TrainerProfile.objects.get_or_create(user=trainer_user)
                if employee_id:
                    profile.employee_id = employee_id
                profile.specialization = specialization
                profile.department = department
                profile.save()

                AuditLog.objects.create(
                    user=request.user,
                    action='TRAINER_EDITED',
                    details=f"Admin edited trainer '{trainer_user.username}' (ID: {trainer_user.id})"
                )
                messages.success(request, f"Trainer '{trainer_user.get_full_name() or trainer_user.username}' updated successfully.")
            return redirect('admin_trainers')

        elif action == 'delete':
            trainer_id = request.POST.get('trainer_id')
            trainer_user = get_object_or_404(User, id=trainer_id, role='TRAINER')
            trainer_name = trainer_user.get_full_name() or trainer_user.username
            AuditLog.objects.create(
                user=request.user,
                action='TRAINER_DELETED',
                details=f"Admin deleted trainer '{trainer_user.username}' (ID: {trainer_id})"
            )
            trainer_user.delete()
            messages.success(request, f"Trainer '{trainer_name}' deleted successfully.")
            return redirect('admin_trainers')

        elif action == 'toggle_status':
            trainer_id = request.POST.get('trainer_id')
            trainer_user = get_object_or_404(User, id=trainer_id, role='TRAINER')
            trainer_user.is_active = not trainer_user.is_active
            trainer_user.save()
            status_text = "activated" if trainer_user.is_active else "deactivated"
            messages.info(request, f"Trainer '{trainer_user.username}' has been {status_text}.")
            return redirect('admin_trainers')

    trainers = User.objects.filter(role='TRAINER').select_related('trainer_profile').prefetch_related('assigned_courses').order_by('-date_joined')
    courses = Course.objects.filter(is_active=True).order_by('name')
    return render(request, 'admin_portal/trainers.html', {'trainers': trainers, 'courses': courses})


@trainer_required
def admin_students(request):
    """Student account management with search, filter, credential emails, and bulk CSV upload. Accessible by Admins and Trainers with course-based isolation."""
    handled_courses = request.user.get_handled_courses().filter(is_active=True)
    handled_batches = request.user.get_handled_batches().filter(is_active=True)
    redirect_target = request.path

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create':
            username = request.POST.get('username', '').strip()
            email = request.POST.get('email', '').strip()
            password = request.POST.get('password', '').strip() or 'Student@123'
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            reg_no = request.POST.get('reg_no', '').strip()
            course_id = request.POST.get('course')
            batch_id = request.POST.get('batch')

            # Validate course permission for trainer
            course = None
            if course_id:
                course = handled_courses.filter(id=course_id).first()
                if not course and not request.user.is_super_admin:
                    messages.error(request, "Permission Denied: You cannot assign students to a course you do not handle.")
                    return redirect(redirect_target)
            elif not request.user.is_super_admin:
                if handled_courses.count() == 1:
                    course = handled_courses.first()
                else:
                    messages.error(request, "Please select one of your assigned courses for this student.")
                    return redirect(redirect_target)

            batch = handled_batches.filter(id=batch_id).first() if batch_id else None

            if User.objects.filter(username=username).exists():
                messages.error(request, f"Username '{username}' already exists.")
            elif StudentProfile.objects.filter(reg_no=reg_no).exists():
                messages.error(request, f"Registration No '{reg_no}' is already registered.")
            else:
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

                # Auto-assign active exams for this course & batch
                if course:
                    active_exams = Exam.objects.filter(course=course, status__in=['PUBLISHED', 'SCHEDULED'])
                    if batch:
                        active_exams = active_exams.filter(Q(batch=batch) | Q(batch__isnull=True))
                    for ex in active_exams:
                        ExamAssignment.objects.get_or_create(exam=ex, student=user)

                AuditLog.objects.create(
                    user=request.user,
                    action='STUDENT_CREATED',
                    details=f"{request.user.role} {request.user.username} created student {username} ({reg_no}) for course {course.code if course else 'None'}"
                )

                # Send welcome email with credentials
                if email:
                    sent, note = send_student_welcome_email(user, password, request=request)
                    if sent:
                        messages.success(request, f"Student '{username}' added successfully and login credentials have been emailed to {email}.")
                    else:
                        messages.warning(request, f"Student '{username}' added successfully. Note: {note}")
                else:
                    messages.success(request, f"Student '{username}' added successfully. (No email provided; default password is '{password}').")
            return redirect(redirect_target)

        elif action == 'edit':
            student_id = request.POST.get('student_id')
            # Security: Ensure trainers can only edit their own students
            if request.user.is_super_admin:
                student_user = get_object_or_404(User, id=student_id, role='STUDENT')
            else:
                student_user = get_object_or_404(request.user.get_visible_students(), id=student_id)

            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            email = request.POST.get('email', '').strip()
            reg_no = request.POST.get('reg_no', '').strip()
            course_id = request.POST.get('course')
            batch_id = request.POST.get('batch')
            new_password = request.POST.get('password', '').strip()
            is_active = request.POST.get('is_active') in ('on', 'true', '1', True, 'ACTIVE')

            course = None
            if course_id:
                course = handled_courses.filter(id=course_id).first()
                if not course and not request.user.is_super_admin:
                    messages.error(request, "Permission Denied: You cannot assign students to a course you do not handle.")
                    return redirect(redirect_target)
            batch = handled_batches.filter(id=batch_id).first() if batch_id else None

            if reg_no and StudentProfile.objects.filter(reg_no=reg_no).exclude(user=student_user).exists():
                messages.error(request, f"Registration No '{reg_no}' is already registered to another candidate.")
            else:
                student_user.first_name = first_name
                student_user.last_name = last_name
                student_user.email = email
                student_user.is_active = is_active
                password_changed = False
                if new_password:
                    student_user.set_password(new_password)
                    password_changed = True
                student_user.save()

                profile, _ = StudentProfile.objects.get_or_create(user=student_user)
                if reg_no:
                    profile.reg_no = reg_no
                profile.course = course
                profile.batch = batch
                profile.save()

                # Sync exam assignments if course/batch changed
                if course:
                    active_exams = Exam.objects.filter(course=course, status__in=['PUBLISHED', 'SCHEDULED'])
                    if batch:
                        active_exams = active_exams.filter(Q(batch=batch) | Q(batch__isnull=True))
                    for ex in active_exams:
                        ExamAssignment.objects.get_or_create(exam=ex, student=student_user)

                AuditLog.objects.create(
                    user=request.user,
                    action='STUDENT_EDITED',
                    details=f"{request.user.role} {request.user.username} edited student '{student_user.username}' (Reg No: {reg_no})"
                )

                if password_changed and student_user.email:
                    send_student_password_reset_email(student_user, new_password, request=request)
                    messages.success(request, f"Student '{student_user.get_full_name() or student_user.username}' updated and new password sent via email.")
                else:
                    messages.success(request, f"Student '{student_user.get_full_name() or student_user.username}' updated successfully.")
            return redirect(redirect_target)

        elif action == 'bulk_upload':
            csv_file = request.FILES.get('csv_file')
            bulk_course_id = request.POST.get('course')
            bulk_batch_id = request.POST.get('batch')

            bulk_course = None
            if bulk_course_id:
                bulk_course = handled_courses.filter(id=bulk_course_id).first()
            elif not request.user.is_super_admin and handled_courses.count() == 1:
                bulk_course = handled_courses.first()

            bulk_batch = handled_batches.filter(id=bulk_batch_id).first() if bulk_batch_id else None

            if not csv_file or not csv_file.name.endswith('.csv'):
                messages.error(request, "Please upload a valid CSV file.")
                return redirect(redirect_target)

            decoded_file = csv_file.read().decode('utf-8', errors='ignore')
            io_string = io.StringIO(decoded_file)
            reader = csv.DictReader(io_string)

            created_count = 0
            emails_sent = 0
            for row in reader:
                uname = row.get('username', '').strip()
                rno = row.get('reg_no', '').strip()
                pwd = row.get('password', '').strip() or 'Student@123'
                fname = row.get('first_name', '').strip()
                lname = row.get('last_name', '').strip()
                email = row.get('email', '').strip()

                if uname and rno and not User.objects.filter(username=uname).exists() and not StudentProfile.objects.filter(reg_no=rno).exists():
                    u = User.objects.create_user(
                        username=uname,
                        email=email,
                        password=pwd,
                        role='STUDENT',
                        first_name=fname,
                        last_name=lname
                    )
                    StudentProfile.objects.create(
                        user=u,
                        reg_no=rno,
                        course=bulk_course,
                        batch=bulk_batch
                    )
                    if bulk_course:
                        for ex in Exam.objects.filter(course=bulk_course, status__in=['PUBLISHED', 'SCHEDULED']):
                            ExamAssignment.objects.get_or_create(exam=ex, student=u)

                    created_count += 1
                    if email:
                        sent, _ = send_student_welcome_email(u, pwd, request=request)
                        if sent:
                            emails_sent += 1

            AuditLog.objects.create(
                user=request.user,
                action='STUDENTS_BULK_UPLOADED',
                details=f"{request.user.role} {request.user.username} bulk created {created_count} students ({emails_sent} credential emails dispatched)"
            )
            messages.success(request, f"Bulk import complete: {created_count} students created ({emails_sent} credential emails sent).")
            return redirect(redirect_target)

        elif action == 'bulk_deactivate':
            student_ids = request.POST.getlist('student_ids')
            # Security: restrict to visible students
            allowed_ids = list(request.user.get_visible_students().filter(id__in=student_ids).values_list('id', flat=True))
            count = User.objects.filter(id__in=allowed_ids, role='STUDENT').update(is_active=False)
            AuditLog.objects.create(
                user=request.user,
                action='STUDENTS_BULK_DEACTIVATED',
                details=f"{request.user.role} {request.user.username} deactivated {count} student account(s)."
            )
            messages.warning(request, f"{count} student account(s) deactivated.")
            return redirect(redirect_target)

        elif action == 'bulk_delete_students':
            student_ids = request.POST.getlist('student_ids')
            # Security: restrict to visible students
            users_to_delete = request.user.get_visible_students().filter(id__in=student_ids)
            count = users_to_delete.count()
            names = list(users_to_delete.values_list('username', flat=True))
            users_to_delete.delete()
            AuditLog.objects.create(
                user=request.user,
                action='STUDENTS_BULK_DELETED',
                details=f"{request.user.role} {request.user.username} permanently deleted {count} student(s): {names}"
            )
            messages.success(request, f"{count} student account(s) permanently deleted.")
            return redirect(redirect_target)

    # Filtering
    query = request.GET.get('q', '').strip()
    course_filter = request.GET.get('course', '').strip()
    batch_filter = request.GET.get('batch', '').strip()

    students = request.user.get_visible_students().select_related(
        'student_profile', 'student_profile__batch', 'student_profile__course'
    ).prefetch_related('student_profile__course__trainers')

    total_student_count = students.count()
    active_student_count = students.filter(is_active=True).count()
    inactive_student_count = total_student_count - active_student_count

    if course_filter and course_filter.isdigit():
        students = students.filter(student_profile__course_id=int(course_filter))
    if batch_filter and batch_filter.isdigit():
        students = students.filter(student_profile__batch_id=int(batch_filter))
    if query:
        students = students.filter(
            Q(username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(student_profile__reg_no__icontains=query)
        )

    return render(request, 'admin_portal/students.html', {
        'students': students.order_by('-date_joined'),
        'courses': handled_courses,
        'batches': handled_batches,
        'query': query,
        'course_filter': course_filter,
        'batch_filter': batch_filter,
        'total_student_count': total_student_count,
        'active_student_count': active_student_count,
        'inactive_student_count': inactive_student_count,
        'has_handled_courses': handled_courses.exists(),
    })


@admin_required
def admin_courses(request):
    """Course catalog view — create, edit, and delete courses with multiple assigned trainers."""
    if request.method == 'POST':
        action = request.POST.get('action', 'create')

        if action == 'edit':
            course_id = request.POST.get('course_id')
            course = get_object_or_404(Course, id=course_id)
            code = request.POST.get('code', '').strip().upper()
            name = request.POST.get('name', '').strip()
            description = request.POST.get('description', '').strip()
            trainer_ids = request.POST.getlist('trainers') or request.POST.getlist('trainers[]')

            if Course.objects.filter(code=code).exclude(id=course.id).exists():
                messages.error(request, f"Course code '{code}' is already used by another course.")
            else:
                course.code = code
                course.name = name
                course.description = description
                course.save()
                course.trainers.set(trainer_ids)
                messages.success(request, f"Course '{name}' updated successfully.")

        elif action == 'delete':
            course_id = request.POST.get('course_id')
            course = get_object_or_404(Course, id=course_id)
            course_name = course.name
            course.delete()
            messages.success(request, f"Course '{course_name}' has been deleted.")

        else:
            code = request.POST.get('code', '').strip().upper()
            name = request.POST.get('name', '').strip()
            description = request.POST.get('description', '').strip()
            trainer_ids = request.POST.getlist('trainers') or request.POST.getlist('trainers[]')

            if Course.objects.filter(code=code).exists():
                messages.error(request, f"Course code '{code}' already exists.")
            else:
                c = Course.objects.create(code=code, name=name, description=description)
                if trainer_ids:
                    c.trainers.set(trainer_ids)
                messages.success(request, f"Course '{name}' added successfully.")

        return redirect('admin_courses')

    courses = Course.objects.prefetch_related('trainers').annotate(batches_count=Count('batches')).order_by('name')
    trainers = User.objects.filter(role='TRAINER', is_active=True).select_related('trainer_profile').order_by('first_name', 'username')
    return render(request, 'admin_portal/courses.html', {
        'courses': courses,
        'trainers': trainers
    })


@admin_required
def admin_batches(request):
    """Batch management — create, edit, delete batches with multiple trainers support."""
    if request.method == 'POST':
        action = request.POST.get('action', 'create')

        if action == 'edit':
            batch_id = request.POST.get('batch_id')
            batch = get_object_or_404(Batch, id=batch_id)
            name = request.POST.get('name', '').strip()
            course_id = request.POST.get('course')
            trainer_ids = request.POST.getlist('trainers') or request.POST.getlist('trainers[]')
            start_date = request.POST.get('start_date') or None
            end_date = request.POST.get('end_date') or None
            is_active = request.POST.get('is_active') in ('on', 'true', '1', True, 'ACTIVE')

            if course_id:
                batch.course = get_object_or_404(Course, id=course_id)
            batch.name = name
            batch.start_date = start_date
            batch.end_date = end_date
            batch.is_active = is_active

            selected_trainers = User.objects.filter(id__in=trainer_ids, role='TRAINER')
            batch.trainers.set(selected_trainers)
            batch.trainer = selected_trainers.first() if selected_trainers.exists() else None
            batch.save()

            AuditLog.objects.create(
                user=request.user,
                action='BATCH_EDITED',
                details=f"Admin updated batch '{batch.name}' (ID: {batch.id}) with {selected_trainers.count()} assigned trainer(s)."
            )
            messages.success(request, f"Batch '{name}' updated successfully.")

        elif action == 'delete':
            batch_id = request.POST.get('batch_id')
            batch = get_object_or_404(Batch, id=batch_id)
            batch_name = batch.name
            AuditLog.objects.create(
                user=request.user,
                action='BATCH_DELETED',
                details=f"Admin deleted batch '{batch_name}' (ID: {batch_id})."
            )
            batch.delete()
            messages.success(request, f"Batch '{batch_name}' deleted successfully.")

        else:
            name = request.POST.get('name', '').strip()
            course_id = request.POST.get('course')
            trainer_ids = request.POST.getlist('trainers') or request.POST.getlist('trainers[]')
            single_trainer = request.POST.get('trainer')
            if not trainer_ids and single_trainer:
                trainer_ids = [single_trainer]

            start_date = request.POST.get('start_date') or None
            end_date = request.POST.get('end_date') or None

            course = get_object_or_404(Course, id=course_id)
            selected_trainers = User.objects.filter(id__in=trainer_ids, role='TRAINER')
            primary_trainer = selected_trainers.first()

            batch = Batch.objects.create(
                name=name,
                course=course,
                trainer=primary_trainer,
                start_date=start_date,
                end_date=end_date
            )
            if selected_trainers.exists():
                batch.trainers.set(selected_trainers)

            AuditLog.objects.create(
                user=request.user,
                action='BATCH_CREATED',
                details=f"Admin created batch '{name}' with {selected_trainers.count()} assigned trainer(s)."
            )
            messages.success(request, f"Batch '{name}' created successfully with assigned trainer(s).")

        return redirect('admin_batches')

    batches = Batch.objects.select_related('course', 'trainer').prefetch_related('trainers').annotate(students_count=Count('students')).order_by('-created_at')
    courses = Course.objects.filter(is_active=True).prefetch_related('trainers')
    trainers = User.objects.filter(role='TRAINER', is_active=True).select_related('trainer_profile').order_by('first_name', 'username')
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

@admin_required
def admin_retakes(request):
    """Super Admin retake request management — approve or reject student retake requests."""
    from django.utils import timezone

    if request.method == 'POST':
        action = request.POST.get('action')
        request_id = request.POST.get('request_id')
        admin_notes = request.POST.get('admin_notes', '').strip()

        retake_req = get_object_or_404(ExamRetakeRequest, id=request_id)

        if action == 'approve':
            # Delete old Result and ExamSession so student can retake
            Result.objects.filter(exam=retake_req.exam, student=retake_req.student).delete()
            ExamSession.objects.filter(exam=retake_req.exam, student=retake_req.student).delete()

            # Reset assignment back to ASSIGNED
            assignment = ExamAssignment.objects.filter(
                exam=retake_req.exam, student=retake_req.student
            ).first()
            if assignment:
                assignment.status = 'ASSIGNED'
                assignment.save()

            retake_req.status = 'APPROVED'
            retake_req.admin_notes = admin_notes or 'Approved by Super Admin.'
            retake_req.reviewed_by = request.user
            retake_req.reviewed_at = timezone.now()
            retake_req.save()

            AuditLog.objects.create(
                user=request.user,
                action='RETAKE_APPROVED',
                details=f"Super Admin approved retake for student '{retake_req.student.username}' on exam '{retake_req.exam.title}'."
            )
            messages.success(request, f"Retake approved for {retake_req.student.get_full_name() or retake_req.student.username}. The student can now retake '{retake_req.exam.title}'.")

        elif action == 'reject':
            retake_req.status = 'REJECTED'
            retake_req.admin_notes = admin_notes or 'Rejected by Super Admin.'
            retake_req.reviewed_by = request.user
            retake_req.reviewed_at = timezone.now()
            retake_req.save()

            AuditLog.objects.create(
                user=request.user,
                action='RETAKE_REJECTED',
                details=f"Super Admin rejected retake for student '{retake_req.student.username}' on exam '{retake_req.exam.title}'."
            )
            messages.info(request, f"Retake request from {retake_req.student.get_full_name() or retake_req.student.username} has been rejected.")

        elif action == 'delete':
            student_name = retake_req.student.get_full_name() or retake_req.student.username
            exam_name = retake_req.exam.title
            retake_req.delete()

            AuditLog.objects.create(
                user=request.user,
                action='RETAKE_DELETED',
                details=f"Super Admin deleted retake request for student '{student_name}' on exam '{exam_name}'."
            )
            messages.success(request, f"Retake request for '{student_name}' on '{exam_name}' has been deleted.")

        return redirect('admin_retakes')

    # Filter by status
    status_filter = request.GET.get('status', '')
    retake_requests = ExamRetakeRequest.objects.select_related('exam', 'student', 'reviewed_by').all()
    if status_filter:
        retake_requests = retake_requests.filter(status=status_filter)

    pending_count = ExamRetakeRequest.objects.filter(status='PENDING').count()

    return render(request, 'admin_portal/retakes.html', {
        'retake_requests': retake_requests,
        'pending_count': pending_count,
        'status_filter': status_filter,
    })


# ==============================================================================
# LEADERBOARD & STUDENT RESULTS REPORTING (OFFICE & ADMIN USE)
# ==============================================================================

def _get_filtered_results(request):
    """Internal helper to retrieve and filter student exam results for UI and exports, isolated by course for trainers."""
    results = Result.objects.select_related(
        'student',
        'student__student_profile',
        'student__student_profile__batch',
        'exam',
        'exam__course',
        'exam__batch',
        'session'
    ).all()

    if not request.user.is_super_admin:
        handled_courses = request.user.get_handled_courses()
        results = results.filter(
            Q(exam__course__in=handled_courses) |
            Q(student__student_profile__course__in=handled_courses)
        )

    exam_id = request.GET.get('exam_id', '').strip()
    batch_id = request.GET.get('batch_id', '').strip()
    status = request.GET.get('status', '').strip().upper()
    search = request.GET.get('search', '').strip()

    if exam_id and exam_id.isdigit():
        results = results.filter(exam_id=int(exam_id))
    if batch_id and batch_id.isdigit():
        results = results.filter(
            Q(exam__batch_id=int(batch_id)) | Q(student__student_profile__batch_id=int(batch_id))
        )
    if status == 'PASS':
        results = results.filter(is_passed=True)
    elif status == 'FAIL':
        results = results.filter(is_passed=False)
    if search:
        results = results.filter(
            Q(student__username__icontains=search) |
            Q(student__first_name__icontains=search) |
            Q(student__last_name__icontains=search) |
            Q(student__student_profile__student_id__icontains=search) |
            Q(exam__title__icontains=search)
        )

    # Clean ordering: Highest percentage first, highest score, then earlier submission
    results = results.order_by('-percentage', '-score', '-created_at')
    return results, exam_id, batch_id, status, search


@trainer_required
def admin_leaderboard(request):
    """
    Super Admin & Trainer Leaderboard and Student Results Hub.
    Displays ranked results, performance metrics, and export capabilities for office use.
    """
    results_qs, exam_id, batch_id, status_filter, search_query = _get_filtered_results(request)

    # Enrich each result with leaderboard ranks & visual badges
    ranked_results = []
    for idx, r in enumerate(results_qs, start=1):
        r.rank = idx
        if idx == 1:
            r.rank_class = 'rank-badge-1'
            r.medal = '🥇'
            r.podium_class = 'podium-gold'
        elif idx == 2:
            r.rank_class = 'rank-badge-2'
            r.medal = '🥈'
            r.podium_class = 'podium-silver'
        elif idx == 3:
            r.rank_class = 'rank-badge-3'
            r.medal = '🥉'
            r.podium_class = 'podium-bronze'
        else:
            r.rank_class = 'rank-badge-other'
            r.medal = f'#{idx}'
            r.podium_class = ''
        ranked_results.append(r)

    top_3 = ranked_results[:3]
    total_count = len(ranked_results)
    passed_count = sum(1 for r in ranked_results if r.is_passed)
    failed_count = total_count - passed_count
    pass_rate = round((passed_count / total_count * 100), 1) if total_count > 0 else 0.0
    avg_score = round(sum(float(r.percentage) for r in ranked_results) / total_count, 1) if total_count > 0 else 0.0
    top_score = float(ranked_results[0].percentage) if ranked_results else 0.0

    exams = request.user.get_visible_exams().order_by('-start_time')
    batches = request.user.get_handled_batches().order_by('name')

    selected_exam = None
    if exam_id and exam_id.isdigit():
        selected_exam = Exam.objects.filter(id=int(exam_id)).first()

    selected_batch = None
    if batch_id and batch_id.isdigit():
        selected_batch = Batch.objects.filter(id=int(batch_id)).first()

    context = {
        'results': ranked_results,
        'top_3': top_3,
        'total_count': total_count,
        'passed_count': passed_count,
        'failed_count': failed_count,
        'pass_rate': pass_rate,
        'avg_score': avg_score,
        'top_score': top_score,
        'exams': exams,
        'batches': batches,
        'selected_exam': selected_exam,
        'selected_exam_id': int(exam_id) if exam_id and exam_id.isdigit() else None,
        'selected_batch': selected_batch,
        'selected_batch_id': int(batch_id) if batch_id and batch_id.isdigit() else None,
        'selected_status': status_filter,
        'search_query': search_query,
    }
    return render(request, 'admin_portal/leaderboard.html', context)


@trainer_required
def admin_export_results_csv(request):
    """Export filtered leaderboard and student results to CSV format for office use."""
    results_qs, _, _, _, _ = _get_filtered_results(request)

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    response['Content-Disposition'] = f'attachment; filename="SATX_Student_Results_Leaderboard_{timestamp}.csv"'

    # Write UTF-8 BOM so Excel opens Indian names and symbols cleanly
    response.write('\ufeff')

    writer = csv.writer(response)
    writer.writerow([
        'Rank',
        'Student Name',
        'Username',
        'Student ID / Roll No',
        'Course',
        'Batch',
        'Exam Title',
        'Exam Type',
        'Marks Obtained',
        'Total Marks',
        'Percentage (%)',
        'Status',
        'Tab Switches',
        'Proctoring Violations',
        'Completed At'
    ])

    for idx, r in enumerate(results_qs, start=1):
        profile = getattr(r.student, 'student_profile', None)
        student_id = profile.student_id if profile else 'N/A'
        batch_name = profile.batch.name if profile and profile.batch else (r.exam.batch.name if r.exam.batch else 'General')
        course_name = r.exam.course.name if r.exam.course else 'General'
        full_name = r.student.get_full_name() or r.student.username

        tab_switches = r.session.tab_switch_count if r.session else 0
        face_violations = (r.session.face_absence_count + r.session.multi_face_count) if r.session else 0

        writer.writerow([
            idx,
            full_name,
            r.student.username,
            student_id,
            course_name,
            batch_name,
            r.exam.title,
            r.exam.get_exam_type_display(),
            float(r.score),
            float(r.exam.total_marks),
            f"{float(r.percentage):.2f}%",
            'PASS' if r.is_passed else 'FAIL',
            tab_switches,
            face_violations,
            r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else 'N/A'
        ])

    return response


@trainer_required
def admin_export_results_pdf(request):
    """
    Generate an official PUMO TECHNOVATION student examination report and leaderboard PDF
    for office administration, record keeping, and student ranking certification.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, KeepTogether, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import inch

    results_qs, exam_id, batch_id, status_filter, search_query = _get_filtered_results(request)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=30,
        rightMargin=30,
        topMargin=30,
        bottomMargin=30
    )

    elements = []
    styles = getSampleStyleSheet()

    # Custom typography styles
    title_style = ParagraphStyle(
        'PumoTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=17,
        textColor=colors.HexColor('#0a192f'),
        alignment=0
    )
    meta_style = ParagraphStyle(
        'PumoMeta',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#334155')
    )
    header_col_style = ParagraphStyle(
        'ColHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.white,
        alignment=1
    )
    cell_style = ParagraphStyle(
        'CellText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#1e293b')
    )
    cell_bold_style = ParagraphStyle(
        'CellBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#0a192f')
    )

    # Logo + Title Header Table
    logo_path = os.path.join(settings.BASE_DIR, 'static', 'images', 'satx_logo.png')
    header_row = []
    if os.path.exists(logo_path):
        try:
            img = RLImage(logo_path, width=1.1*inch, height=0.9*inch)
            header_row.append(img)
        except Exception:
            header_row.append(Paragraph("<b>[SATX LOGO]</b>", meta_style))
    else:
        header_row.append(Paragraph("<b>SATX</b>", meta_style))

    brand_text = """
    <b><font size="12" color="#0a192f">SATX EXAM PORTAL</font></b><br/>
    <font color="#0f4c81" size="10"><b>OFFICIAL STUDENT RESULTS REPORT</b></font><br/>
    <font color="#64748b" size="8">Online Examination Assessment &amp; Evaluation Record</font><br/>
    <font color="#334155" size="8">Generated On: <b>{}</b> &bull; Authorized Officer: <b>{}</b></font>
    """.format(
        timezone.now().strftime('%d %B %Y, %I:%M %p'),
        request.user.get_full_name() or request.user.username
    )

    header_row.append(Paragraph(brand_text, meta_style))
    header_table = Table([header_row], colWidths=[1.1*inch, 6.3*inch])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(header_table)
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#0f4c81'), spaceAfter=8))

    # Summary Stats Block
    total_count = results_qs.count()
    passed_count = sum(1 for r in results_qs if r.is_passed)
    failed_count = total_count - passed_count
    pass_pct = (passed_count / total_count * 100) if total_count > 0 else 0
    top_score = results_qs.first().percentage if total_count > 0 else 0

    stats_data = [
        [
            Paragraph(f"<b>Total Candidates:</b> {total_count}", meta_style),
            Paragraph(f"<b>Passed:</b> <font color='#10b981'><b>{passed_count}</b></font>", meta_style),
            Paragraph(f"<b>Failed:</b> <font color='#ef4444'><b>{failed_count}</b></font>", meta_style),
            Paragraph(f"<b>Pass Rate:</b> <b>{pass_pct:.1f}%</b>", meta_style),
            Paragraph(f"<b>High Score:</b> <b>{top_score:.1f}%</b>", meta_style),
        ]
    ]
    stats_table = Table(stats_data, colWidths=[1.48*inch]*5)
    stats_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f1f5f9')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e1')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('PADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(stats_table)
    elements.append(Spacer(1, 10))

    # Leaderboard Table
    table_headers = [
        Paragraph("<b>Rank</b>", header_col_style),
        Paragraph("<b>Student Name</b>", header_col_style),
        Paragraph("<b>Student ID</b>", header_col_style),
        Paragraph("<b>Batch</b>", header_col_style),
        Paragraph("<b>Exam Title</b>", header_col_style),
        Paragraph("<b>Marks</b>", header_col_style),
        Paragraph("<b>%</b>", header_col_style),
        Paragraph("<b>Status</b>", header_col_style),
    ]
    rows = [table_headers]

    for idx, r in enumerate(results_qs, start=1):
        profile = getattr(r.student, 'student_profile', None)
        stu_id = profile.student_id if profile else '-'
        batch_n = profile.batch.name if profile and profile.batch else '-'
        stu_name = r.student.get_full_name() or r.student.username

        rank_str = f"#{idx}"
        if idx == 1:
            rank_str = "1 (Gold)"
        elif idx == 2:
            rank_str = "2 (Silver)"
        elif idx == 3:
            rank_str = "3 (Bronze)"

        status_text = f"<font color='{'#10b981' if r.is_passed else '#ef4444'}'><b>{'PASS' if r.is_passed else 'FAIL'}</b></font>"

        rows.append([
            Paragraph(f"<b>{rank_str}</b>", cell_bold_style),
            Paragraph(stu_name, cell_bold_style),
            Paragraph(stu_id, cell_style),
            Paragraph(batch_n, cell_style),
            Paragraph(r.exam.title[:24], cell_style),
            Paragraph(f"{float(r.score):.1f}/{float(r.exam.total_marks):.0f}", cell_style),
            Paragraph(f"{float(r.percentage):.1f}%", cell_bold_style),
            Paragraph(status_text, cell_style),
        ])

    if len(rows) == 1:
        rows.append([Paragraph("<i>No examination results recorded for the selected criteria.</i>", cell_style)] + [Paragraph("", cell_style)]*7)

    col_widths = [0.75*inch, 1.8*inch, 1.05*inch, 0.95*inch, 1.5*inch, 0.7*inch, 0.6*inch, 0.65*inch]
    t = Table(rows, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f4c81')),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('PADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 20))

    # Official Sign-off Block
    sign_data = [
        [
            Paragraph("___________________________________<br/><b>Prepared &amp; Verified By:</b><br/>Trainer / Controller of Examinations<br/>SATX Exam Portal", meta_style),
            Paragraph("___________________________________<br/><b>Authorized Office Approval:</b><br/>Branch Head / Centre Administrator<br/>SATX Exam Portal", meta_style),
        ]
    ]
    sign_table = Table(sign_data, colWidths=[3.7*inch, 3.7*inch])
    sign_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
    ]))
    elements.append(KeepTogether([sign_table]))

    doc.build(elements)
    buffer.seek(0)

    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="SATX_Official_Student_Results_Report_{timestamp}.pdf"'
    return response


@login_required
def admin_student_single_report(request, result_id):
    """
    Printable individual student result card & marksheet for office documentation and students.
    """
    result = get_object_or_404(
        Result.objects.select_related(
            'student',
            'student__student_profile',
            'student__student_profile__batch',
            'exam',
            'exam__course',
            'session'
        ),
        id=result_id
    )

    # Permission: Staff/Trainers can view reports of their handled courses; Students can view their own report
    is_admin = request.user.is_super_admin
    is_trainer = request.user.is_trainer
    if not is_admin and not is_trainer and result.student != request.user:
        messages.error(request, "Permission denied.")
        return redirect('student_results')

    if is_trainer:
        handled_courses = request.user.get_handled_courses()
        course_match = result.exam.course in handled_courses
        student_course_match = (
            getattr(result.student, 'student_profile', None) and
            result.student.student_profile.course in handled_courses
        )
        if not course_match and not student_course_match:
            messages.error(request, "Permission Denied: You do not handle the course for this student result.")
            return redirect('admin_leaderboard')

    # Fetch individual answers breakdown
    answers = []
    if result.session:
        answers = StudentAnswer.objects.filter(session=result.session).select_related('question').order_by('question__id')

    try:
        total_m = float(result.exam.total_marks or 0)
        scored_m = float(result.score or 0)
        not_obtained_m = max(0.0, total_m - scored_m)
        pct_val = float(result.percentage or 0)
    except (ValueError, TypeError):
        not_obtained_m = 0.0
        pct_val = 0.0

    context = {
        'result': result,
        'student': result.student,
        'profile': getattr(result.student, 'student_profile', None),
        'exam': result.exam,
        'session': result.session,
        'answers': answers,
        'marks_not_obtained': f"{not_obtained_m:.2f}",
        'percentage_val': pct_val,
    }
    return render(request, 'admin_portal/student_report_card.html', context)


@login_required
def admin_toggle_answers_approval(request, result_id):
    """Trainer or Admin approves/revokes release of detailed answers to the candidate."""
    if not (request.user.role in ('ADMIN', 'SUPER_ADMIN', 'TRAINER') or request.user.is_superuser):
        messages.error(request, "Permission denied.")
        return redirect('dashboard_redirect')

    result = get_object_or_404(Result, id=result_id)
    if request.user.is_trainer:
        handled_courses = request.user.get_handled_courses()
        course_match = result.exam.course in handled_courses
        student_course_match = (
            getattr(result.student, 'student_profile', None) and
            result.student.student_profile.course in handled_courses
        )
        if not course_match and not student_course_match:
            messages.error(request, "Permission Denied: You do not handle the course for this student result.")
            return redirect('admin_leaderboard')

    result.answers_approved = not result.answers_approved
    result.save()

    status_msg = "approved and released to candidate" if result.answers_approved else "hidden from candidate"
    messages.success(request, f"Answers for '{result.student.get_full_name() or result.student.username}' on '{result.exam.title}' are now {status_msg}.")

    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect('admin_leaderboard')


