import json
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db import transaction
from django.contrib.auth.decorators import login_required

from accounts.models import User
from accounts.decorators import trainer_required, student_required
from portal.models import Course, Batch, AuditLog
from exams.models import (
    Question, QuestionOption, PDFQuestionImport, Exam, ExamQuestion,
    ExamAssignment, ExamSession, StudentAnswer, ProctoringEvent, Result
)
from exams.pdf_parser import extract_questions_from_pdf


# ==========================================
# TRAINER VIEWS
# ==========================================

@trainer_required
def trainer_dashboard(request):
    """Trainer main control dashboard."""
    assigned_batches = Batch.objects.filter(trainer=request.user)
    my_exams = Exam.objects.filter(created_by=request.user)
    active_exams = my_exams.filter(status='PUBLISHED')
    total_questions = Question.objects.filter(created_by=request.user).count()
    pending_approvals = Question.objects.filter(created_by=request.user, is_approved=False).count()
    total_alerts = ProctoringEvent.objects.filter(session__exam__created_by=request.user, is_reviewed=False).count()

    context = {
        'assigned_batches': assigned_batches,
        'my_exams': my_exams[:5],
        'active_exams_count': active_exams.count(),
        'total_questions': total_questions,
        'pending_approvals': pending_approvals,
        'total_alerts': total_alerts,
    }
    return render(request, 'trainer/dashboard.html', context)


@trainer_required
def question_bank(request):
    """Question Bank with filtering, searching, and manual creation."""
    courses = Course.objects.filter(is_active=True)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create_mcq':
            q_text = request.POST.get('question_text', '').strip()
            course_id = request.POST.get('course')
            topic = request.POST.get('topic', 'General').strip()
            difficulty = request.POST.get('difficulty', 'MEDIUM')
            marks = int(request.POST.get('marks', 1))
            explanation = request.POST.get('explanation', '').strip()
            correct_opt = request.POST.get('correct_option', 'A')

            course = Course.objects.filter(id=course_id).first() if course_id else None

            q = Question.objects.create(
                question_type='MCQ_SINGLE',
                course=course,
                topic=topic,
                difficulty=difficulty,
                question_text=q_text,
                marks=marks,
                explanation=explanation,
                created_by=request.user,
                is_approved=True
            )

            for letter in ['A', 'B', 'C', 'D']:
                opt_text = request.POST.get(f'option_{letter.lower()}', '').strip()
                if opt_text:
                    QuestionOption.objects.create(
                        question=q,
                        option_letter=letter,
                        option_text=opt_text,
                        is_correct=(letter == correct_opt)
                    )

            messages.success(request, "MCQ Question added to Question Bank.")
            return redirect('question_bank')

        elif action == 'create_coding':
            q_text = request.POST.get('question_text', '').strip()
            course_id = request.POST.get('course')
            topic = request.POST.get('topic', 'Coding').strip()
            difficulty = request.POST.get('difficulty', 'MEDIUM')
            marks = int(request.POST.get('marks', 10))
            input_format = request.POST.get('input_format', '')
            output_format = request.POST.get('output_format', '')
            sample_in = request.POST.get('sample_input', '')
            sample_out = request.POST.get('sample_output', '')
            hidden_in = request.POST.get('hidden_input', '')
            hidden_out = request.POST.get('hidden_output', '')

            course = Course.objects.filter(id=course_id).first() if course_id else None

            Question.objects.create(
                question_type='CODING',
                course=course,
                topic=topic,
                difficulty=difficulty,
                question_text=q_text,
                marks=marks,
                input_format=input_format,
                output_format=output_format,
                sample_input=sample_in,
                sample_output=sample_out,
                hidden_input=hidden_in,
                hidden_output=hidden_out,
                created_by=request.user,
                is_approved=True
            )
            messages.success(request, "Coding Problem added to Question Bank.")
            return redirect('question_bank')

        elif action == 'create_practical':
            q_text = request.POST.get('question_text', '').strip()
            course_id = request.POST.get('course')
            marks = int(request.POST.get('marks', 20))
            eval_criteria = request.POST.get('evaluation_criteria', '')

            course = Course.objects.filter(id=course_id).first() if course_id else None

            Question.objects.create(
                question_type='PRACTICAL',
                course=course,
                question_text=q_text,
                marks=marks,
                evaluation_criteria=eval_criteria,
                created_by=request.user,
                is_approved=True
            )
            messages.success(request, "Practical Task added to Question Bank.")
            return redirect('question_bank')

    # Filter questions
    q_type = request.GET.get('type')
    q_diff = request.GET.get('diff')
    q_query = request.GET.get('q')

    questions = Question.objects.filter(is_approved=True).prefetch_related('options')
    if q_type:
        questions = questions.filter(question_type=q_type)
    if q_diff:
        questions = questions.filter(difficulty=q_diff)
    if q_query:
        questions = questions.filter(question_text__icontains=q_query)

    return render(request, 'trainer/question_bank.html', {
        'questions': questions,
        'courses': courses,
    })


@trainer_required
def pdf_import(request):
    """Upload PDF question paper, extract text/options, and display for review."""
    courses = Course.objects.filter(is_active=True)

    if request.method == 'POST':
        pdf_file = request.FILES.get('pdf_file')
        course_id = request.POST.get('course')
        course = Course.objects.filter(id=course_id).first() if course_id else None

        if not pdf_file or not pdf_file.name.endswith('.pdf'):
            messages.error(request, "Please upload a valid PDF document.")
            return redirect('pdf_import')

        # Create import record
        import_rec = PDFQuestionImport.objects.create(
            trainer=request.user,
            pdf_file=pdf_file,
            status='PENDING'
        )

        extracted_items, err = extract_questions_from_pdf(import_rec.pdf_file.path)
        if err or not extracted_items:
            import_rec.status = 'FAILED'
            import_rec.error_message = err or "Could not extract structured questions."
            import_rec.save()
            messages.error(request, f"Extraction warning: {import_rec.error_message}")
            return redirect('pdf_import')

        # Create unapproved questions for trainer review
        created_count = 0
        for item in extracted_items:
            q = Question.objects.create(
                question_type='MCQ_SINGLE',
                course=course,
                topic='PDF Import',
                question_text=item['text'],
                marks=item.get('marks', 2),
                created_by=request.user,
                is_approved=False
            )
            corr_letter = item.get('correct_answer')
            for opt_letter, opt_val in item['options'].items():
                QuestionOption.objects.create(
                    question=q,
                    option_letter=opt_letter,
                    option_text=opt_val,
                    is_correct=(opt_letter == corr_letter)
                )
            created_count += 1

        import_rec.status = 'EXTRACTED'
        import_rec.extracted_count = created_count
        import_rec.save()

        messages.success(request, f"Extracted {created_count} questions from '{pdf_file.name}'. Please review and approve them below.")
        return redirect('pdf_review', import_id=import_rec.id)

    recent_imports = PDFQuestionImport.objects.filter(trainer=request.user).order_by('-uploaded_at')[:10]
    return render(request, 'trainer/pdf_import.html', {
        'courses': courses,
        'recent_imports': recent_imports
    })


@trainer_required
def pdf_review(request, import_id):
    """Trainer approval interface for extracted PDF questions."""
    pending_questions = Question.objects.filter(created_by=request.user, is_approved=False).prefetch_related('options')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'approve_single':
            q_id = request.POST.get('question_id')
            q = get_object_or_404(Question, id=q_id, created_by=request.user)
            # update correct answer
            corr_letter = request.POST.get('correct_option')
            for opt in q.options.all():
                opt.is_correct = (opt.option_letter == corr_letter)
                opt.save()
            q.is_approved = True
            q.save()
            messages.success(request, f"Question #{q.id} approved into Question Bank.")

        elif action == 'approve_all':
            for q in pending_questions:
                q.is_approved = True
                q.save()
            messages.success(request, f"Approved all {pending_questions.count()} questions into Question Bank.")
            return redirect('question_bank')

        return redirect('pdf_review', import_id=import_id)

    return render(request, 'trainer/pdf_review.html', {
        'pending_questions': pending_questions,
        'import_id': import_id
    })


@trainer_required
def create_exam(request):
    """Exam scheduler and question picker."""
    courses = Course.objects.filter(is_active=True)
    batches = Batch.objects.filter(is_active=True)
    approved_questions = Question.objects.filter(is_approved=True)

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        course_id = request.POST.get('course')
        batch_id = request.POST.get('batch')
        exam_type = request.POST.get('exam_type', 'MCQ')
        duration = int(request.POST.get('duration_minutes', 60))
        pass_marks = int(request.POST.get('pass_marks', 40))
        start_time = request.POST.get('start_time')
        end_time = request.POST.get('end_time')
        is_proctored = request.POST.get('is_proctored') == 'on'
        status = request.POST.get('status', 'PUBLISHED')

        selected_q_ids = request.POST.getlist('selected_questions')

        course = get_object_or_404(Course, id=course_id)
        batch = Batch.objects.filter(id=batch_id).first() if batch_id else None

        total_marks = 0
        questions_to_add = Question.objects.filter(id__in=selected_q_ids)
        for q in questions_to_add:
            total_marks += q.marks

        exam = Exam.objects.create(
            title=title,
            description=description,
            course=course,
            batch=batch,
            exam_type=exam_type,
            duration_minutes=duration,
            total_marks=total_marks or 100,
            pass_marks=pass_marks,
            start_time=start_time,
            end_time=end_time,
            status=status,
            created_by=request.user,
            is_proctored=is_proctored
        )

        for idx, q in enumerate(questions_to_add, start=1):
            ExamQuestion.objects.create(exam=exam, question=q, order=idx, marks=q.marks)

        # Assign to students in batch
        if batch:
            for student_profile in batch.students.all():
                ExamAssignment.objects.get_or_create(exam=exam, student=student_profile.user)

        messages.success(request, f"Exam '{title}' created and published successfully!")
        return redirect('trainer_dashboard')

    return render(request, 'trainer/create_exam.html', {
        'courses': courses,
        'batches': batches,
        'questions': approved_questions
    })


@trainer_required
def live_monitoring(request):
    """Trainer view of active sessions and proctoring telemetry."""
    active_sessions = ExamSession.objects.filter(is_submitted=False).select_related('exam', 'student')
    proctoring_alerts = ProctoringEvent.objects.select_related('session__student', 'session__exam').order_by('-timestamp')[:50]

    return render(request, 'trainer/live_monitoring.html', {
        'active_sessions': active_sessions,
        'proctoring_alerts': proctoring_alerts
    })


# ==========================================
# STUDENT VIEWS & EXAM ROOM
# ==========================================

@student_required
def student_dashboard(request):
    """Student portal dashboard showing assigned examinations and scores."""
    assignments = ExamAssignment.objects.filter(student=request.user).select_related('exam', 'exam__course')
    completed_results = Result.objects.filter(student=request.user, is_published=True).select_related('exam')

    return render(request, 'student/dashboard.html', {
        'assignments': assignments,
        'completed_results': completed_results
    })


@student_required
def exam_instructions(request, exam_id):
    """Pre-exam instruction page and webcam compatibility check."""
    exam = get_object_or_404(Exam, id=exam_id, status='PUBLISHED')

    # Verify student assignment
    assignment = get_object_or_404(ExamAssignment, exam=exam, student=request.user)
    if assignment.status == 'COMPLETED':
        messages.info(request, "You have already completed this examination.")
        return redirect('student_results')

    return render(request, 'student/exam_instructions.html', {
        'exam': exam,
        'assignment': assignment
    })


@student_required
def take_exam(request, exam_id):
    """Distraction-free examination room with countdown timer and AI proctoring."""
    exam = get_object_or_404(Exam, id=exam_id, status='PUBLISHED')
    assignment = get_object_or_404(ExamAssignment, exam=exam, student=request.user)

    if assignment.status == 'COMPLETED':
        messages.info(request, "You have already submitted this examination.")
        return redirect('student_results')

    # Create or retrieve ongoing session
    session, _ = ExamSession.objects.get_or_create(
        exam=exam,
        student=request.user,
        is_submitted=False,
        defaults={'ip_address': request.META.get('REMOTE_ADDR')}
    )

    if session.is_submitted or session.tab_switch_count > 3:
        messages.error(request, "This examination was terminated and submitted because you exceeded 3 tab-switching warnings.")
        return redirect('student_results')

    assignment.status = 'IN_PROGRESS'
    assignment.save()

    # Calculate remaining time in seconds
    elapsed_seconds = (timezone.now() - session.start_time).total_seconds()
    total_seconds = exam.duration_minutes * 60
    remaining_seconds = max(0, int(total_seconds - elapsed_seconds))

    if remaining_seconds <= 0:
        # Time expired, auto-submit
        return redirect('submit_exam', session_id=session.id)

    # Load questions and existing answers
    exam_questions = ExamQuestion.objects.filter(exam=exam).select_related('question').prefetch_related('question__options')
    saved_answers = {a.question_id: a.selected_option_letter for a in session.answers.all()}

    questions_data = []
    for eq in exam_questions:
        q = eq.question
        options = list(q.options.all())
        questions_data.append({
            'id': q.id,
            'text': q.question_text,
            'type': q.question_type,
            'marks': eq.marks,
            'options': [{'letter': opt.option_letter, 'text': opt.option_text} for opt in options],
            'saved_answer': saved_answers.get(q.id, ''),
        })

    return render(request, 'student/take_exam.html', {
        'exam': exam,
        'session': session,
        'remaining_seconds': remaining_seconds,
        'questions_json': json.dumps(questions_data),
        'questions_count': len(questions_data),
        'initial_tab_switches': session.tab_switch_count
    })


@csrf_exempt
@require_POST
@login_required
def save_answer_api(request):
    """AJAX endpoint for instant answer auto-saving."""
    try:
        data = json.loads(request.body)
        session_id = data.get('session_id')
        question_id = data.get('question_id')
        selected_option = data.get('selected_option', '').strip().upper()
        is_review = data.get('is_review', False)

        session = get_object_or_404(ExamSession, id=session_id, student=request.user, is_submitted=False)
        question = get_object_or_404(Question, id=question_id)

        with transaction.atomic():
            answer, _ = StudentAnswer.objects.get_or_create(session=session, question=question)
            answer.selected_option_letter = selected_option
            answer.is_marked_for_review = is_review
            answer.save()

        return JsonResponse({'status': 'success', 'message': 'Answer auto-saved.'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@csrf_exempt
@require_POST
@login_required
def proctoring_event_api(request):
    """AJAX endpoint for receiving client-side webcam proctoring alerts."""
    try:
        data = json.loads(request.body)
        session_id = data.get('session_id')
        event_type = data.get('event_type')
        details = data.get('details', '')

        session = get_object_or_404(ExamSession, id=session_id, student=request.user, is_submitted=False)

        severity = 'MEDIUM'
        if event_type == 'MULTIPLE_FACES':
            severity = 'HIGH'
            session.multi_face_count += 1
        elif event_type == 'FACE_ABSENT':
            severity = 'MEDIUM'
            session.face_absence_count += 1
        elif event_type in ['TAB_SWITCH', 'FULLSCREEN_EXIT']:
            severity = 'HIGH'
            session.tab_switch_count += 1
        session.save()

        ProctoringEvent.objects.create(
            session=session,
            event_type=event_type,
            severity=severity,
            details=details
        )

        is_terminated = session.tab_switch_count > 3
        return JsonResponse({
            'status': 'recorded',
            'tab_switch_count': session.tab_switch_count,
            'is_terminated': is_terminated
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@login_required
def submit_exam(request, session_id):
    """Final examination submission and automatic scoring with tab switch termination support."""
    session = get_object_or_404(ExamSession, id=session_id, student=request.user)
    reason = request.GET.get('reason') or request.POST.get('reason') or ''
    was_terminated = (reason == 'tab_switch_violation') or (session.tab_switch_count > 3)

    if not session.is_submitted:
        with transaction.atomic():
            session.is_submitted = True
            session.end_time = timezone.now()
            session.save()

            exam = session.exam

            # Auto-evaluate MCQs
            total_score = Decimal('0.0')
            correct_count = 0
            wrong_count = 0

            exam_questions = ExamQuestion.objects.filter(exam=exam).select_related('question')
            for eq in exam_questions:
                q = eq.question
                student_ans = StudentAnswer.objects.filter(session=session, question=q).first()
                if student_ans and student_ans.selected_option_letter:
                    correct_opt = q.options.filter(is_correct=True).first()
                    if correct_opt and correct_opt.option_letter == student_ans.selected_option_letter:
                        student_ans.marks_obtained = eq.marks
                        student_ans.is_evaluated = True
                        student_ans.save()
                        total_score += Decimal(str(eq.marks))
                        correct_count += 1
                    else:
                        student_ans.marks_obtained = 0
                        student_ans.is_evaluated = True
                        student_ans.save()
                        wrong_count += 1
                else:
                    wrong_count += 1

            total_marks = Decimal(str(exam.total_marks or 100))
            percentage = (total_score / total_marks * 100) if total_marks > 0 else Decimal('0.0')
            is_passed = total_score >= Decimal(str(exam.pass_marks))

            feedback = "Terminated due to multiple tab switch violations (Exceeded 3 warnings)." if was_terminated else ""

            # Create or update Result
            Result.objects.update_or_create(
                exam=exam,
                student=request.user,
                defaults={
                    'session': session,
                    'total_questions': exam_questions.count(),
                    'correct_answers': correct_count,
                    'wrong_answers': wrong_count,
                    'score': total_score,
                    'percentage': percentage,
                    'is_passed': is_passed,
                    'is_published': True,
                    'trainer_feedback': feedback,
                    'published_at': timezone.now()
                }
            )

            # Update assignment status
            assignment = ExamAssignment.objects.filter(exam=exam, student=request.user).first()
            if assignment:
                assignment.status = 'COMPLETED'
                assignment.save()

    if was_terminated:
        messages.error(request, "Your examination was automatically terminated and submitted because you exceeded 3 tab-switching warnings.")
    else:
        messages.success(request, "Your examination has been submitted successfully.")
    return redirect('student_results')


@student_required
def student_results(request):
    """View personal published results."""
    results = Result.objects.filter(student=request.user, is_published=True).select_related('exam', 'session')
    return render(request, 'student/results.html', {'results': results})
