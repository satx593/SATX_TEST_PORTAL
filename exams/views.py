import json
import io
import os
import tempfile
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
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
    """Trainer main control dashboard isolated to courses handled by this trainer."""
    handled_courses = request.user.get_handled_courses().filter(is_active=True)
    assigned_batches = request.user.get_handled_batches().filter(is_active=True)
    my_exams = request.user.get_visible_exams().select_related('course', 'batch').order_by('-created_at')
    active_exams = my_exams.filter(status='PUBLISHED')
    total_questions = request.user.get_visible_questions().count()
    pending_approvals = Question.objects.filter(is_approved=False).filter(
        Q(created_by=request.user) | Q(course__in=handled_courses)
    ).distinct().count()
    total_alerts = ProctoringEvent.objects.filter(
        session__exam__course__in=handled_courses, is_reviewed=False
    ).count() if not request.user.is_super_admin else ProctoringEvent.objects.filter(is_reviewed=False).count()
    assigned_students_count = request.user.get_visible_students().count()
    total_students_count = assigned_students_count if not request.user.is_super_admin else User.objects.filter(role='STUDENT').count()

    context = {
        'handled_courses': handled_courses,
        'assigned_batches': assigned_batches,
        'my_exams': my_exams[:5],
        'total_exams_count': my_exams.count(),
        'active_exams_count': active_exams.count(),
        'total_questions': total_questions,
        'pending_approvals': pending_approvals,
        'total_alerts': total_alerts,
        'total_students_count': total_students_count,
        'assigned_students_count': assigned_students_count,
        'has_handled_courses': handled_courses.exists(),
    }
    return render(request, 'trainer/dashboard.html', context)


def _process_test_cases(post_data):
    """
    Extracts multiple sample and hidden test cases from POST data.
    Supports both dynamic arrays (sample_inputs[], sample_outputs[])
    and single textarea with '---' delimiter.
    """
    sample_inps = post_data.getlist('sample_inputs[]') or post_data.getlist('sample_inputs')
    sample_outs = post_data.getlist('sample_outputs[]') or post_data.getlist('sample_outputs')
    if sample_inps or sample_outs:
        clean_inps = []
        clean_outs = []
        for i in range(max(len(sample_inps), len(sample_outs))):
            inp = sample_inps[i].strip() if i < len(sample_inps) else ''
            out = sample_outs[i].strip() if i < len(sample_outs) else ''
            if inp or out:
                clean_inps.append(inp)
                clean_outs.append(out)
        sample_in = '\n---\n'.join(clean_inps)
        sample_out = '\n---\n'.join(clean_outs)
    else:
        sample_in = post_data.get('sample_input', '').strip()
        sample_out = post_data.get('sample_output', '').strip()

    hidden_inps = post_data.getlist('hidden_inputs[]') or post_data.getlist('hidden_inputs')
    hidden_outs = post_data.getlist('hidden_outputs[]') or post_data.getlist('hidden_outputs')
    if hidden_inps or hidden_outs:
        clean_inps = []
        clean_outs = []
        for i in range(max(len(hidden_inps), len(hidden_outs))):
            inp = hidden_inps[i].strip() if i < len(hidden_inps) else ''
            out = hidden_outs[i].strip() if i < len(hidden_outs) else ''
            if inp or out:
                clean_inps.append(inp)
                clean_outs.append(out)
        hidden_in = '\n---\n'.join(clean_inps)
        hidden_out = '\n---\n'.join(clean_outs)
    else:
        hidden_in = post_data.get('hidden_input', '').strip()
        hidden_out = post_data.get('hidden_output', '').strip()

    return sample_in, sample_out, hidden_in, hidden_out


@trainer_required
def question_bank(request):
    """Question Bank with filtering, searching, and manual creation, isolated by course."""
    handled_courses = request.user.get_handled_courses().filter(is_active=True)
    visible_questions = request.user.get_visible_questions()

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

            course = None
            if course_id:
                course = handled_courses.filter(id=course_id).first()
                if not course and not request.user.is_super_admin:
                    messages.error(request, "Permission Denied: You cannot create questions for a course you do not handle.")
                    return redirect('question_bank')
            elif not request.user.is_super_admin:
                if handled_courses.count() == 1:
                    course = handled_courses.first()
                else:
                    messages.error(request, "Please select one of your assigned courses.")
                    return redirect('question_bank')

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

            messages.success(request, f"MCQ Question added to Question Bank ({course.code if course else 'General'}).")
            return redirect('question_bank')

        elif action == 'create_coding':
            q_text = request.POST.get('question_text', '').strip()
            course_id = request.POST.get('course')
            topic = request.POST.get('topic', 'Coding').strip() or 'Coding'
            difficulty = request.POST.get('difficulty', 'MEDIUM')
            marks = int(request.POST.get('marks', 10))
            input_format = request.POST.get('input_format', '').strip()
            output_format = request.POST.get('output_format', '').strip()
            constraints = request.POST.get('constraints', '').strip()
            sample_in, sample_out, hidden_in, hidden_out = _process_test_cases(request.POST)

            course = None
            if course_id:
                course = handled_courses.filter(id=course_id).first()
                if not course and not request.user.is_super_admin:
                    messages.error(request, "Permission Denied: You cannot create questions for a course you do not handle.")
                    return redirect('question_bank')
            elif not request.user.is_super_admin:
                if handled_courses.count() == 1:
                    course = handled_courses.first()
                else:
                    messages.error(request, "Please select one of your assigned courses.")
                    return redirect('question_bank')

            Question.objects.create(
                question_type='CODING',
                course=course,
                topic=topic,
                difficulty=difficulty,
                question_text=q_text,
                marks=marks,
                input_format=input_format,
                output_format=output_format,
                constraints=constraints,
                sample_input=sample_in,
                sample_output=sample_out,
                hidden_input=hidden_in,
                hidden_output=hidden_out,
                created_by=request.user,
                is_approved=True
            )
            messages.success(request, f"Coding Problem with test cases added to Question Bank ({course.code if course else 'General'}).")
            return redirect('question_bank')

        elif action == 'create_practical':
            q_text = request.POST.get('question_text', '').strip()
            course_id = request.POST.get('course')
            marks = int(request.POST.get('marks', 20))
            eval_criteria = request.POST.get('evaluation_criteria', '')

            course = None
            if course_id:
                course = handled_courses.filter(id=course_id).first()
                if not course and not request.user.is_super_admin:
                    messages.error(request, "Permission Denied: You cannot create questions for a course you do not handle.")
                    return redirect('question_bank')
            elif not request.user.is_super_admin:
                if handled_courses.count() == 1:
                    course = handled_courses.first()
                else:
                    messages.error(request, "Please select one of your assigned courses.")
                    return redirect('question_bank')

            Question.objects.create(
                question_type='PRACTICAL',
                course=course,
                question_text=q_text,
                marks=marks,
                evaluation_criteria=eval_criteria,
                created_by=request.user,
                is_approved=True
            )
            messages.success(request, f"Practical Task added to Question Bank ({course.code if course else 'General'}).")
            return redirect('question_bank')

        elif action == 'create_theory':
            q_text = request.POST.get('question_text', '').strip()
            course_id = request.POST.get('course')
            topic = request.POST.get('topic', 'Theory').strip() or 'Theory'
            difficulty = request.POST.get('difficulty', 'MEDIUM')
            marks = int(request.POST.get('marks', 1))
            keywords = request.POST.get('keywords', '').strip()
            explanation = request.POST.get('explanation', '').strip()

            course = None
            if course_id:
                course = handled_courses.filter(id=course_id).first()
                if not course and not request.user.is_super_admin:
                    messages.error(request, "Permission Denied: You cannot create questions for a course you do not handle.")
                    return redirect('question_bank')
            elif not request.user.is_super_admin:
                if handled_courses.count() == 1:
                    course = handled_courses.first()
                else:
                    messages.error(request, "Please select one of your assigned courses.")
                    return redirect('question_bank')

            Question.objects.create(
                question_type='THEORY',
                course=course,
                topic=topic,
                difficulty=difficulty,
                question_text=q_text,
                marks=marks,
                keywords=keywords,
                explanation=explanation,
                created_by=request.user,
                is_approved=True
            )
            messages.success(request, f"Theory Question added to Question Bank ({course.code if course else 'General'}).")
            return redirect('question_bank')

        elif action == 'edit_question':
            q_id = request.POST.get('question_id')
            q = get_object_or_404(visible_questions, id=q_id)
            q.question_text = request.POST.get('question_text', '').strip()
            q.topic = request.POST.get('topic', '').strip() or 'General'
            q.difficulty = request.POST.get('difficulty', 'MEDIUM')
            q.marks = int(request.POST.get('marks', 1))
            course_id = request.POST.get('course')
            if course_id:
                new_course = handled_courses.filter(id=course_id).first()
                if new_course or request.user.is_super_admin:
                    q.course = new_course

            if q.question_type == 'MCQ_SINGLE':
                q.explanation = request.POST.get('explanation', '').strip()
                corr_letter = request.POST.get('correct_option', 'A').strip().upper()
                for letter in ['A', 'B', 'C', 'D']:
                    new_text = request.POST.get(f'option_{letter.lower()}', '').strip()
                    if new_text:
                        opt, _ = QuestionOption.objects.get_or_create(question=q, option_letter=letter)
                        opt.option_text = new_text
                        opt.is_correct = (letter == corr_letter)
                        opt.save()
            elif q.question_type == 'THEORY':
                q.keywords = request.POST.get('keywords', '').strip()
                q.explanation = request.POST.get('explanation', '').strip()
            elif q.question_type == 'CODING':
                q.input_format = request.POST.get('input_format', '').strip()
                q.output_format = request.POST.get('output_format', '').strip()
                q.constraints = request.POST.get('constraints', '').strip()
                sample_in, sample_out, hidden_in, hidden_out = _process_test_cases(request.POST)
                q.sample_input = sample_in
                q.sample_output = sample_out
                q.hidden_input = hidden_in
                q.hidden_output = hidden_out
            elif q.question_type == 'PRACTICAL':
                q.evaluation_criteria = request.POST.get('evaluation_criteria', '').strip()
            q.save()
            messages.success(request, f"Question Q{q.id} updated successfully.")
            referer = request.META.get('HTTP_REFERER')
            if referer:
                return redirect(referer)
            return redirect('question_bank')

        elif action == 'delete_question':
            q_id = request.POST.get('question_id')
            q = get_object_or_404(visible_questions, id=q_id)
            q.delete()
            messages.success(request, "Question deleted from Question Bank.")
            referer = request.META.get('HTTP_REFERER')
            if referer:
                return redirect(referer)
            return redirect('question_bank')

        elif action == 'bulk_delete_questions':
            q_ids = request.POST.getlist('question_ids')
            deleted_count, _ = visible_questions.filter(id__in=q_ids).delete()
            messages.success(request, f"{deleted_count} question(s) deleted from the Question Bank.")
            return redirect('question_bank')

    # Filter questions
    q_type = request.GET.get('type')
    q_diff = request.GET.get('diff')
    q_course = request.GET.get('course')
    q_query = request.GET.get('q')

    questions = visible_questions.filter(is_approved=True).select_related('course').prefetch_related('options').order_by('id')
    if q_type:
        questions = questions.filter(question_type=q_type)
    if q_diff:
        questions = questions.filter(difficulty=q_diff)
    if q_course and q_course.isdigit():
        questions = questions.filter(course_id=int(q_course))
    if q_query:
        questions = questions.filter(question_text__icontains=q_query)

    return render(request, 'trainer/question_bank.html', {
        'questions': questions,
        'courses': handled_courses,
        'selected_course': q_course,
        'has_handled_courses': handled_courses.exists(),
    })


@trainer_required
def quick_edit_question(request, question_id):
    """
    AJAX & Form handler to edit any Question directly from
    Create Exam, Edit Exam, or Question Bank.
    """
    q = get_object_or_404(request.user.get_visible_questions(), id=question_id)

    if request.method == 'POST':
        q.question_text = request.POST.get('question_text', '').strip()
        q.topic = request.POST.get('topic', '').strip() or 'General'
        q.difficulty = request.POST.get('difficulty', 'MEDIUM')
        q.marks = int(request.POST.get('marks', q.marks or 1))
        course_id = request.POST.get('course')
        if course_id:
            new_course = request.user.get_handled_courses().filter(id=course_id).first()
            if new_course or request.user.is_super_admin:
                q.course = new_course

        if q.question_type == 'MCQ_SINGLE':
            q.explanation = request.POST.get('explanation', '').strip()
            corr_letter = request.POST.get('correct_option', 'A').strip().upper()
            for letter in ['A', 'B', 'C', 'D']:
                opt_text = request.POST.get(f'option_{letter.lower()}', '').strip()
                if opt_text:
                    opt, _ = QuestionOption.objects.get_or_create(question=q, option_letter=letter)
                    opt.option_text = opt_text
                    opt.is_correct = (letter == corr_letter)
                    opt.save()

        elif q.question_type == 'THEORY':
            q.keywords = request.POST.get('keywords', '').strip()
            q.explanation = request.POST.get('explanation', '').strip()

        elif q.question_type == 'CODING':
            q.input_format = request.POST.get('input_format', '').strip()
            q.output_format = request.POST.get('output_format', '').strip()
            q.constraints = request.POST.get('constraints', '').strip()
            sample_in, sample_out, hidden_in, hidden_out = _process_test_cases(request.POST)
            q.sample_input = sample_in
            q.sample_output = sample_out
            q.hidden_input = hidden_in
            q.hidden_output = hidden_out

        elif q.question_type == 'PRACTICAL':
            q.evaluation_criteria = request.POST.get('evaluation_criteria', '').strip()

        q.save()

        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('is_ajax') == 'true':
            return JsonResponse({
                'success': True,
                'question_id': q.id,
                'question_text': q.question_text,
                'marks': q.marks,
                'topic': q.topic,
                'difficulty': q.difficulty,
                'question_type': q.question_type,
                'type_display': q.get_question_type_display(),
            })

        messages.success(request, f"Question Q{q.id} updated successfully.")
        referer = request.META.get('HTTP_REFERER')
        if referer:
            return redirect(referer)
        return redirect('question_bank')

    return JsonResponse({'error': 'Method not allowed'}, status=405)


@trainer_required
def get_question_json(request, question_id):
    """Return complete question data as JSON for the interactive Edit modal."""
    q = get_object_or_404(request.user.get_visible_questions(), id=question_id)
    options = [{'letter': o.option_letter, 'text': o.option_text, 'is_correct': o.is_correct} for o in q.options.all().order_by('option_letter')]

    return JsonResponse({
        'id': q.id,
        'question_text': q.question_text,
        'question_type': q.question_type,
        'type_display': q.get_question_type_display(),
        'topic': q.topic,
        'difficulty': q.difficulty,
        'marks': q.marks,
        'course_id': q.course_id,
        'explanation': q.explanation,
        'keywords': q.keywords or '',
        'input_format': q.input_format,
        'output_format': q.output_format,
        'constraints': q.constraints,
        'options': options,
        'sample_cases': q.get_sample_test_cases(),
        'hidden_cases': q.get_hidden_test_cases(),
        'evaluation_criteria': q.evaluation_criteria,
    })



@trainer_required
def pdf_import(request):
    """Upload PDF question paper, extract questions, and display for review."""
    courses = request.user.get_handled_courses().filter(is_active=True)

    if request.method == 'POST':
        pdf_file = request.FILES.get('pdf_file')
        course_id = request.POST.get('course')
        course = courses.filter(id=course_id).first() if course_id else None

        if not course and not request.user.is_super_admin:
            if courses.count() == 1:
                course = courses.first()
            else:
                messages.error(
                    request,
                    "Please select one of your assigned courses."
                )
                return redirect('pdf_import')

        if not pdf_file or not pdf_file.name.lower().endswith('.pdf'):
            messages.error(request, "Please upload a valid PDF document.")
            return redirect('pdf_import')

        # Create import record using existing remote storage
        import_rec = PDFQuestionImport.objects.create(
            trainer=request.user,
            pdf_file=pdf_file,
            status='PENDING'
        )

        try:
            # Download PDF from Cloudinary/remote storage
            # and temporarily save it inside Vercel's /tmp directory.
            with import_rec.pdf_file.open("rb") as pdf:
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    suffix=".pdf",
                    dir="/tmp"
                ) as temp_pdf:

                    while True:
                        chunk = pdf.read(1024 * 1024)
                        if not chunk:
                            break
                        temp_pdf.write(chunk)

                    temp_pdf.flush()

                    # IMPORTANT: Extract before closing temp_pdf.
                    extracted_items, err = extract_questions_from_pdf(
                        temp_pdf.name
                    )

            if err or not extracted_items:
                import_rec.status = 'FAILED'
                import_rec.error_message = (
                    err or "Could not extract structured questions."
                )
                import_rec.save()

                messages.error(
                    request,
                    f"Extraction warning: {import_rec.error_message}"
                )
                return redirect('pdf_import')

        except Exception as e:
            import_rec.status = 'FAILED'
            import_rec.error_message = str(e)
            import_rec.save()

            messages.error(
                request,
                f"PDF processing failed: {str(e)}"
            )
            return redirect('pdf_import')

        # Create unapproved questions for trainer review
        created_count = 0

        try:
            for item in extracted_items:
                q = Question.objects.create(
                    question_type='MCQ_SINGLE',
                    course=course,
                    topic='PDF Import',
                    question_text=item['text'],
                    marks=item.get('marks', 1),
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

        except Exception as e:
            import_rec.status = 'FAILED'
            import_rec.error_message = str(e)
            import_rec.save()

            messages.error(
                request,
                f"Question saving failed: {str(e)}"
            )
            return redirect('pdf_import')

        messages.success(
            request,
            f"Extracted {created_count} questions from "
            f"'{pdf_file.name}' for course "
            f"{course.code if course else 'General'}. "
            "Please review and approve them below."
        )

        return redirect('pdf_review', import_id=import_rec.id)

    recent_imports = PDFQuestionImport.objects.filter(
        trainer=request.user
    ).order_by('-uploaded_at')[:10]

    return render(request, 'trainer/pdf_import.html', {
        'courses': courses,
        'recent_imports': recent_imports,
        'has_handled_courses': courses.exists(),
    })


@trainer_required
def pdf_review(request, import_id=0):
    """Trainer approval interface for extracted PDF questions with approve and delete/cancel options."""
    visible_courses = request.user.get_handled_courses()
    pending_questions = Question.objects.filter(is_approved=False).prefetch_related('options').order_by('id')
    if not request.user.is_super_admin:
        pending_questions = pending_questions.filter(Q(created_by=request.user) | Q(course__in=visible_courses)).distinct()

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'approve_single':
            q_id = request.POST.get('question_id')
            q = get_object_or_404(Question, id=q_id, created_by=request.user)
            # Update question text if edited
            q_text = request.POST.get('question_text', '').strip()
            if q_text:
                q.question_text = q_text

            # Update option texts and correct answer
            corr_letter = request.POST.get('correct_option')
            for opt in q.options.all():
                opt_key = f'option_{opt.option_letter.lower()}'
                edited_opt_text = request.POST.get(opt_key, '').strip()
                if edited_opt_text:
                    opt.option_text = edited_opt_text
                opt.is_correct = (opt.option_letter == corr_letter)
                opt.save()

            q.is_approved = True
            q.save()
            messages.success(request, "Question approved into Question Bank with verified options.")

        elif action in ('delete_single', 'reject_single', 'cancel_single'):
            q_id = request.POST.get('question_id')
            q = get_object_or_404(Question, id=q_id, created_by=request.user, is_approved=False)
            q.delete()
            messages.success(request, f"Question #{q_id} cancelled and deleted from approval queue.")

        elif action == 'approve_all':
            count = pending_questions.count()
            for q in pending_questions:
                q.is_approved = True
                q.save()
            messages.success(request, f"Approved all {count} questions into Question Bank.")
            return redirect('question_bank')

        elif action in ('delete_all', 'cancel_all', 'reject_all', 'discard_all'):
            count = pending_questions.count()
            pending_questions.delete()
            messages.success(request, f"Cancelled and deleted all {count} pending questions from approval queue.")
            return redirect('question_bank')

        if import_id and import_id != 0:
            return redirect('pdf_review', import_id=import_id)
        return redirect('pdf_review_all')

    return render(request, 'trainer/pdf_review.html', {
        'pending_questions': pending_questions,
        'import_id': import_id
    })


@trainer_required
def create_exam(request):
    """Exam scheduler and question picker isolated to trainer's handled courses."""
    courses = request.user.get_handled_courses().filter(is_active=True)
    batches = request.user.get_handled_batches().filter(is_active=True)
    approved_questions = request.user.get_visible_questions().filter(is_approved=True).select_related('course')

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

        course = get_object_or_404(courses, id=course_id)
        batch = batches.filter(id=batch_id).first() if batch_id else None

        # Preserve exact question sequence from the form (matches PDF extraction order)
        int_ids = [int(qid) for qid in selected_q_ids if str(qid).isdigit()]
        q_dict = {q.id: q for q in approved_questions.filter(id__in=int_ids)}
        ordered_questions = [q_dict[qid] for qid in int_ids if qid in q_dict]

        total_marks = sum(q.marks for q in ordered_questions)

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
            is_proctored=is_proctored,
            shuffle_questions=False,
            shuffle_options=False
        )

        for idx, q in enumerate(ordered_questions, start=1):
            ExamQuestion.objects.create(exam=exam, question=q, order=idx, marks=q.marks)

        # Assign to students:
        # If batch is specified, assign to students of that batch
        # If no batch, assign to ALL students enrolled in this course
        if batch:
            target_students = batch.students.all()
        else:
            target_students = course.students.all()

        for student_profile in target_students:
            ExamAssignment.objects.get_or_create(exam=exam, student=student_profile.user)

        messages.success(request, f"Exam '{title}' created and published successfully for {course.code}!")
        return redirect('trainer_dashboard')

    return render(request, 'trainer/create_exam.html', {
        'courses': courses,
        'batches': batches,
        'questions': approved_questions.order_by('id'),
        'has_handled_courses': courses.exists(),
    })


@trainer_required
def live_monitoring(request):
    """Trainer view of active sessions and proctoring telemetry isolated by handled courses."""
    visible_courses = request.user.get_handled_courses()
    if request.user.is_super_admin:
        active_sessions = ExamSession.objects.filter(is_submitted=False).select_related('exam', 'exam__course', 'student')
        proctoring_alerts = ProctoringEvent.objects.select_related('session__student', 'session__exam', 'session__exam__course').order_by('-timestamp')[:50]
    else:
        active_sessions = ExamSession.objects.filter(
            is_submitted=False, exam__course__in=visible_courses
        ).select_related('exam', 'exam__course', 'student')
        proctoring_alerts = ProctoringEvent.objects.filter(
            session__exam__course__in=visible_courses
        ).select_related('session__student', 'session__exam', 'session__exam__course').order_by('-timestamp')[:50]

    return render(request, 'trainer/live_monitoring.html', {
        'active_sessions': active_sessions,
        'proctoring_alerts': proctoring_alerts,
        'has_handled_courses': visible_courses.exists(),
    })


@trainer_required
def manage_exams(request):
    """Trainer list of all their exams with edit/delete actions, isolated by course."""
    exams = request.user.get_visible_exams().select_related('course', 'batch').order_by('-created_at')
    return render(request, 'trainer/manage_exams.html', {'exams': exams})


@trainer_required
def edit_exam(request, exam_id):
    """Edit an existing exam — title, batch, duration, pass marks, status, and questions."""
    exam = get_object_or_404(request.user.get_visible_exams(), id=exam_id)
    courses = request.user.get_handled_courses().filter(is_active=True)
    batches = request.user.get_handled_batches().filter(is_active=True)
    approved_questions = request.user.get_visible_questions().filter(is_approved=True).select_related('course')
    # IDs of questions already in this exam
    selected_q_ids = set(ExamQuestion.objects.filter(exam=exam).values_list('question_id', flat=True))

    if request.method == 'POST':
        exam.title = request.POST.get('title', exam.title).strip()
        exam.description = request.POST.get('description', '').strip()
        course_id = request.POST.get('course')
        batch_id = request.POST.get('batch')
        if course_id:
            exam.course = get_object_or_404(courses, id=course_id)
        exam.batch = batches.filter(id=batch_id).first() if batch_id else None
        exam.exam_type = request.POST.get('exam_type', exam.exam_type)
        exam.duration_minutes = int(request.POST.get('duration_minutes', exam.duration_minutes))
        exam.pass_marks = int(request.POST.get('pass_marks', exam.pass_marks))
        exam.status = request.POST.get('status', exam.status)
        start_time = request.POST.get('start_time')
        end_time = request.POST.get('end_time')
        if start_time:
            exam.start_time = start_time
        if end_time:
            exam.end_time = end_time
        exam.is_proctored = request.POST.get('is_proctored') == 'on'

        # Update selected questions preserving exact form order
        new_q_ids = request.POST.getlist('selected_questions')
        int_ids = [int(qid) for qid in new_q_ids if str(qid).isdigit()]
        q_dict = {q.id: q for q in Question.objects.filter(id__in=int_ids)}
        ordered_questions = [q_dict[qid] for qid in int_ids if qid in q_dict]

        # Recalculate total marks
        exam.total_marks = sum(q.marks for q in ordered_questions) or exam.total_marks
        exam.shuffle_questions = False
        exam.shuffle_options = False
        exam.save()

        # Rebuild exam questions in exact order
        ExamQuestion.objects.filter(exam=exam).delete()
        for idx, q in enumerate(ordered_questions, start=1):
            ExamQuestion.objects.create(exam=exam, question=q, order=idx, marks=q.marks)

        # If batch changed, re-assign to new batch students (or course students)
        if exam.batch:
            target_students = exam.batch.students.all()
        else:
            target_students = exam.course.students.all()

        for student_profile in target_students:
            ExamAssignment.objects.get_or_create(exam=exam, student=student_profile.user)

        AuditLog.objects.create(
            user=request.user,
            action='EXAM_EDITED',
            details=f"Trainer '{request.user.username}' edited exam '{exam.title}' (ID: {exam.id})."
        )
        messages.success(request, f"Exam '{exam.title}' updated successfully.")
        return redirect('manage_exams')

    return render(request, 'trainer/edit_exam.html', {
        'exam': exam,
        'courses': courses,
        'batches': batches,
        'questions': approved_questions.order_by('id'),
        'selected_q_ids': selected_q_ids,
    })


@trainer_required
@require_POST
def delete_exam(request, exam_id):
    """Permanently delete an exam and all associated data (sessions, answers, results)."""
    exam = get_object_or_404(request.user.get_visible_exams(), id=exam_id)
    exam_title = exam.title
    exam.delete()   # cascades to ExamQuestion, ExamAssignment, ExamSession, StudentAnswer, Result
    AuditLog.objects.create(
        user=request.user,
        action='EXAM_DELETED',
        details=f"Trainer '{request.user.username}' permanently deleted exam '{exam_title}' (ID: {exam_id})."
    )
    messages.success(request, f"Examination '{exam_title}' and all related data have been permanently deleted.")
    return redirect('trainer_dashboard')


# ==========================================
# STUDENT VIEWS & EXAM ROOM
# ==========================================

@student_required
def student_dashboard(request):
    """Student portal dashboard showing assigned examinations and scores for their enrolled course."""
    profile = getattr(request.user, 'student_profile', None)

    # Auto-sync exams for student's enrolled course and batch
    if profile and profile.course:
        applicable_exams = Exam.objects.filter(
            course=profile.course,
            status__in=['PUBLISHED', 'SCHEDULED', 'COMPLETED']
        )
        if profile.batch:
            applicable_exams = applicable_exams.filter(Q(batch=profile.batch) | Q(batch__isnull=True))
        for ex in applicable_exams:
            ExamAssignment.objects.get_or_create(exam=ex, student=request.user)

    if profile and profile.course:
        assignments = ExamAssignment.objects.filter(
            student=request.user,
            exam__course=profile.course
        ).select_related('exam', 'exam__course', 'exam__batch')
        completed_results = Result.objects.filter(
            student=request.user,
            exam__course=profile.course,
            is_published=True
        ).select_related('exam', 'exam__course')
    else:
        assignments = ExamAssignment.objects.none()
        completed_results = Result.objects.none()

    return render(request, 'student/dashboard.html', {
        'assignments': assignments,
        'completed_results': completed_results,
        'student_course': profile.course if profile else None,
        'student_batch': profile.batch if profile else None,
    })


@student_required
def exam_instructions(request, exam_id):
    """Pre-exam instruction page and webcam compatibility check."""
    exam = get_object_or_404(Exam, id=exam_id, status='PUBLISHED')
    profile = getattr(request.user, 'student_profile', None)

    # Verify course enrollment
    if not profile or not profile.course or exam.course_id != profile.course_id:
        messages.error(request, "Access Denied: You are not enrolled in the course for this examination.")
        return redirect('student_dashboard')

    # Verify batch if exam is batch-specific
    if exam.batch and profile.batch_id != exam.batch_id:
        messages.error(request, "Access Denied: This examination is scheduled for another batch.")
        return redirect('student_dashboard')

    # Ensure assignment exists
    assignment, _ = ExamAssignment.objects.get_or_create(exam=exam, student=request.user)
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
    profile = getattr(request.user, 'student_profile', None)

    # Verify course enrollment
    if not profile or not profile.course or exam.course_id != profile.course_id:
        messages.error(request, "Access Denied: You are not enrolled in the course for this examination.")
        return redirect('student_dashboard')

    # Verify batch if exam is batch-specific
    if exam.batch and profile.batch_id != exam.batch_id:
        messages.error(request, "Access Denied: This examination is scheduled for another batch.")
        return redirect('student_dashboard')

    assignment, _ = ExamAssignment.objects.get_or_create(exam=exam, student=request.user)

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

    if session.is_submitted or session.tab_switch_count > 2:
        messages.error(request, "This examination was terminated and submitted because you exceeded 2 tab-switching warnings.")
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

    # Load questions and existing answers strictly in PDF / assignment order
    exam_questions = ExamQuestion.objects.filter(exam=exam).select_related('question').prefetch_related('question__options').order_by('order', 'id')
    saved_answers = {a.question_id: a.selected_option_letter for a in session.answers.all()}
    saved_codes   = {a.question_id: a.submitted_code for a in session.answers.all()}
    saved_theories = {a.question_id: a.theory_answer for a in session.answers.all()}

    # ── CODING EXAM: single-question LeetCode-style room ──────────────────
    coding_qs = [eq for eq in exam_questions if eq.question.question_type == 'CODING']
    if coding_qs:
        # For coding exams, show one question at a time (or the first coding Q)
        eq = coding_qs[0]
        q  = eq.question

        # Support multiple sample test cases split by "---"
        raw_sample_in  = (q.sample_input  or '').strip()
        raw_sample_out = (q.sample_output or '').strip()
        raw_hidden_in  = (q.hidden_input  or '').strip()
        raw_hidden_out = (q.hidden_output or '').strip()

        def split_cases(text):
            parts = [p.strip() for p in text.split('---') if p.strip()]
            return parts if parts else ([text] if text else [])

        sample_inputs  = split_cases(raw_sample_in)
        sample_outputs = split_cases(raw_sample_out)
        hidden_inputs  = split_cases(raw_hidden_in)
        hidden_outputs = split_cases(raw_hidden_out)

        return render(request, 'student/coding_exam_room.html', {
            'exam':              exam,
            'session':           session,
            'question':          q,
            'exam_question':     eq,
            'remaining_seconds': remaining_seconds,
            'initial_tab_switches': session.tab_switch_count,
            'sample_input_json':  json.dumps(sample_inputs),
            'sample_output_json': json.dumps(sample_outputs),
            'hidden_input_json':  json.dumps(hidden_inputs),
            'hidden_output_json': json.dumps(hidden_outputs),
            'saved_code':         saved_codes.get(q.id, ''),
        })

    # ── MCQ / PRACTICAL EXAM: standard exam room ───────────────────────────
    questions_data = []
    for eq in exam_questions:
        q = eq.question
        options = list(q.options.all().order_by('option_letter'))
        questions_data.append({
            'id': q.id,
            'text': q.question_text,
            'type': q.question_type,
            'marks': eq.marks,
            'options': [{'letter': opt.option_letter, 'text': opt.option_text} for opt in options],
            'saved_answer': saved_answers.get(q.id, ''),
            'saved_theory_answer': saved_theories.get(q.id, ''),
            'input_format': q.input_format or '',
            'output_format': q.output_format or '',
            'sample_input': q.sample_input or '',
            'sample_output': q.sample_output or '',
            'hidden_input': q.hidden_input or '',
            'hidden_output': q.hidden_output or '',
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
        theory_answer = data.get('theory_answer', '')
        is_review = data.get('is_review', False)

        session = get_object_or_404(ExamSession, id=session_id, student=request.user, is_submitted=False)
        question = get_object_or_404(Question, id=question_id)

        with transaction.atomic():
            answer, _ = StudentAnswer.objects.get_or_create(session=session, question=question)
            if selected_option:
                answer.selected_option_letter = selected_option
            if 'theory_answer' in data:
                answer.theory_answer = theory_answer
            answer.is_marked_for_review = is_review
            # Save code for coding questions
            submitted_code = data.get('submitted_code', '')
            if submitted_code:
                answer.submitted_code = submitted_code
            answer.save()
            answer.save()

        return JsonResponse({'status': 'success', 'message': 'Answer auto-saved.'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@csrf_exempt
@require_POST
@login_required
def run_code_api(request):
    """Securely execute student Python or Java code and return stdout/stderr.
    Supports: run with custom input, run sample test, run hidden test.
    """
    import subprocess, tempfile, os, sys

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'status': 'error', 'stderr': 'Invalid JSON body.'}, status=400)

    code     = data.get('code', '').strip()
    language = data.get('language', 'python').lower()
    stdin    = data.get('input', '')
    mode     = data.get('mode', 'run')          # 'run' | 'sample' | 'hidden'
    expected = data.get('expected_output', '').strip()

    if not code:
        return JsonResponse({'status': 'error', 'stderr': 'No code submitted.'})

    TIMEOUT = 5  # seconds

    def execute(cmd, cwd=None):
        try:
            result = subprocess.run(
                cmd, input=stdin, capture_output=True, text=True,
                timeout=TIMEOUT, cwd=cwd
            )
            return result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired:
            return '', f'Time Limit Exceeded ({TIMEOUT}s). Check for infinite loops.', -1

    stdout = stderr = ''
    exit_code = 0

    try:
        if language == 'python':
            # Write code to temp file and execute with the same Python interpreter
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                f.write(code)
                tmp_path = f.name
            try:
                stdout, stderr, exit_code = execute([sys.executable, tmp_path])
            finally:
                try: os.unlink(tmp_path)
                except: pass

        elif language == 'java':
            with tempfile.TemporaryDirectory() as tmpdir:
                java_file = os.path.join(tmpdir, 'Main.java')
                with open(java_file, 'w', encoding='utf-8') as f:
                    f.write(code)
                # Compile
                try:
                    comp = subprocess.run(
                        ['javac', java_file], capture_output=True, text=True, timeout=15
                    )
                except FileNotFoundError:
                    return JsonResponse({'status': 'error', 'stdout': '', 'stderr': 'Java (javac) is not installed on this server. Please use Python.'})
                except subprocess.TimeoutExpired:
                    return JsonResponse({'status': 'error', 'stdout': '', 'stderr': 'Java compilation timed out.'})

                if comp.returncode != 0:
                    return JsonResponse({'status': 'compile_error', 'stdout': '', 'stderr': comp.stderr})

                stdout, stderr, exit_code = execute(['java', '-cp', tmpdir, 'Main'], cwd=tmpdir)
        else:
            return JsonResponse({'status': 'error', 'stderr': 'Unsupported language. Choose Python or Java.'})

    except Exception as e:
        return JsonResponse({'status': 'error', 'stdout': '', 'stderr': f'Server error: {str(e)}'})

    actual_output = stdout.strip()
    passed = None
    if mode in ('sample', 'hidden') and expected:
        passed = (actual_output == expected.strip())

    return JsonResponse({
        'status': 'ok' if exit_code == 0 else 'runtime_error',
        'stdout': stdout,
        'stderr': stderr,
        'exit_code': exit_code,
        'actual_output': actual_output,
        'passed': passed,
        'mode': mode,
    })


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

        is_terminated = session.tab_switch_count > 2
        return JsonResponse({
            'status': 'recorded',
            'tab_switch_count': session.tab_switch_count,
            'is_terminated': is_terminated
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


def evaluate_coding_submission(code, question, max_marks):
    """
    Evaluates student code against both sample and hidden test cases for a question.
    Returns: (marks_awarded: Decimal, is_all_passed: bool, passed_tests: int, total_tests: int)
    """
    import subprocess, tempfile, os, sys

    if not code or not code.strip():
        return Decimal('0.0'), False, 0, 0

    code = code.strip()
    is_java = ('public class' in code or 'import java' in code or 'System.out.' in code)
    lang = 'java' if is_java else 'python'

    def split_cases(text):
        if not text:
            return []
        text = str(text).strip()
        if not text:
            return []
        if '---' in text:
            return [p.strip() for p in text.split('---') if p.strip()]
        return [text]

    sample_ins = split_cases(question.sample_input)
    sample_outs = split_cases(question.sample_output)
    hidden_ins = split_cases(question.hidden_input)
    hidden_outs = split_cases(question.hidden_output)

    test_cases = []
    for i in range(len(sample_ins)):
        expected = sample_outs[i] if i < len(sample_outs) else ''
        test_cases.append((sample_ins[i], expected))

    for i in range(len(hidden_ins)):
        expected = hidden_outs[i] if i < len(hidden_outs) else ''
        test_cases.append((hidden_ins[i], expected))

    if not test_cases:
        test_cases.append(('', ''))

    TIMEOUT = 5

    def run_single(stdin_data, tmpdir=None, tmp_path=None):
        try:
            if lang == 'python':
                res = subprocess.run(
                    [sys.executable, tmp_path],
                    input=stdin_data,
                    capture_output=True,
                    text=True,
                    timeout=TIMEOUT
                )
                return res.stdout, res.stderr, res.returncode
            else:
                res = subprocess.run(
                    ['java', '-cp', tmpdir, 'Main'],
                    input=stdin_data,
                    capture_output=True,
                    text=True,
                    timeout=TIMEOUT,
                    cwd=tmpdir
                )
                return res.stdout, res.stderr, res.returncode
        except subprocess.TimeoutExpired:
            return '', 'Timeout', -1
        except Exception as ex:
            return '', str(ex), -1

    passed_count = 0
    total_count = len(test_cases)

    try:
        if lang == 'python':
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                f.write(code)
                tmp_py = f.name
            try:
                for inp, exp in test_cases:
                    stdout, stderr, code_ret = run_single(inp, tmp_path=tmp_py)
                    actual = '\n'.join([line.rstrip() for line in stdout.strip().splitlines()])
                    expected = '\n'.join([line.rstrip() for line in exp.strip().splitlines()])
                    if code_ret == 0 and (not expected or actual == expected):
                        passed_count += 1
            finally:
                try:
                    os.unlink(tmp_py)
                except Exception:
                    pass

        elif lang == 'java':
            with tempfile.TemporaryDirectory() as tmpdir:
                java_file = os.path.join(tmpdir, 'Main.java')
                with open(java_file, 'w', encoding='utf-8') as f:
                    f.write(code)
                comp = subprocess.run(
                    ['javac', java_file],
                    capture_output=True,
                    text=True,
                    timeout=15
                )
                if comp.returncode == 0:
                    for inp, exp in test_cases:
                        stdout, stderr, code_ret = run_single(inp, tmpdir=tmpdir)
                        actual = '\n'.join([line.rstrip() for line in stdout.strip().splitlines()])
                        expected = '\n'.join([line.rstrip() for line in exp.strip().splitlines()])
                        if code_ret == 0 and (not expected or actual == expected):
                            passed_count += 1
                else:
                    passed_count = 0
    except Exception:
        pass

    if total_count > 0:
        ratio = Decimal(str(passed_count)) / Decimal(str(total_count))
        marks_awarded = (ratio * Decimal(str(max_marks))).quantize(Decimal('0.01'))
        is_all_passed = (passed_count == total_count)
    else:
        marks_awarded = Decimal('0.0')
        is_all_passed = False

    return marks_awarded, is_all_passed, passed_count, total_count


@login_required
def submit_exam(request, session_id):
    """Final examination submission and automatic scoring for MCQs and Coding problems with 2-warning tab switch termination support."""
    session = get_object_or_404(ExamSession, id=session_id, student=request.user)
    reason = request.GET.get('reason') or request.POST.get('reason') or ''
    was_terminated = (reason == 'tab_switch_violation') or (session.tab_switch_count > 2)

    # If submitted via POST with code, capture it directly
    submitted_code_post = request.POST.get('submitted_code', '').strip()

    if not session.is_submitted:
        with transaction.atomic():
            session.is_submitted = True
            session.end_time = timezone.now()
            session.save()

            exam = session.exam

            total_score = Decimal('0.0')
            correct_count = 0
            wrong_count = 0

            exam_questions = ExamQuestion.objects.filter(exam=exam).select_related('question').order_by('order', 'id')
            for eq in exam_questions:
                q = eq.question
                student_ans, _ = StudentAnswer.objects.get_or_create(session=session, question=q)

                if q.question_type == 'CODING':
                    code = (student_ans.submitted_code or '').strip()
                    if not code and submitted_code_post:
                        code = submitted_code_post
                        student_ans.submitted_code = code

                    if code:
                        marks_awarded, is_all_passed, passed_t, total_t = evaluate_coding_submission(code, q, eq.marks)
                        student_ans.marks_obtained = marks_awarded
                        student_ans.is_evaluated = True
                        student_ans.save()
                        total_score += marks_awarded
                        if is_all_passed or marks_awarded > 0:
                            correct_count += 1
                        else:
                            wrong_count += 1
                    else:
                        student_ans.marks_obtained = Decimal('0.0')
                        student_ans.is_evaluated = True
                        student_ans.save()
                        wrong_count += 1

                elif q.question_type in ('MCQ_SINGLE', 'MCQ_MULTI'):
                    if student_ans and student_ans.selected_option_letter:
                        correct_opt = q.options.filter(is_correct=True).first()
                        if correct_opt and correct_opt.option_letter == student_ans.selected_option_letter:
                            student_ans.marks_obtained = eq.marks
                            student_ans.is_evaluated = True
                            student_ans.save()
                            total_score += Decimal(str(eq.marks))
                            correct_count += 1
                        else:
                            student_ans.marks_obtained = Decimal('0.0')
                            student_ans.is_evaluated = True
                            student_ans.save()
                            wrong_count += 1
                    else:
                        wrong_count += 1

                elif q.question_type == 'THEORY':
                    student_text = (student_ans.theory_answer or '').strip()
                    if student_text and q.keywords:
                        raw_keywords = [k.strip().lower() for k in q.keywords.split(',') if k.strip()]
                        matched = any(kw in student_text.lower() for kw in raw_keywords)
                        if matched:
                            student_ans.marks_obtained = Decimal(str(eq.marks))
                            student_ans.is_evaluated = True
                            student_ans.save()
                            total_score += Decimal(str(eq.marks))
                            correct_count += 1
                        else:
                            student_ans.marks_obtained = Decimal('0.0')
                            student_ans.is_evaluated = True
                            student_ans.save()
                            wrong_count += 1
                    else:
                        student_ans.marks_obtained = Decimal('0.0')
                        student_ans.is_evaluated = True
                        student_ans.save()
                        wrong_count += 1

                elif q.question_type == 'PRACTICAL':
                    if student_ans.practical_file:
                        student_ans.is_evaluated = False
                        student_ans.save()
                        total_score += Decimal(str(student_ans.marks_obtained or 0))
                    else:
                        wrong_count += 1

            total_marks = Decimal(str(exam.total_marks or 100))
            pass_val = Decimal(str(exam.pass_marks or 0))

            # If pass_marks was entered as a percentage (greater than total_marks):
            if pass_val > total_marks and total_marks > 0:
                pass_threshold = (pass_val / Decimal('100.0')) * total_marks
            else:
                pass_threshold = pass_val

            percentage = ((total_score / total_marks) * 100).quantize(Decimal('0.01')) if total_marks > 0 else Decimal('0.0')
            is_passed = total_score >= pass_threshold

            feedback = "Terminated due to multiple tab switch violations (Exceeded 2 warnings)." if was_terminated else ""

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
        messages.error(request, "Your examination was automatically terminated and submitted because you exceeded 2 tab-switching warnings.")
    else:
        messages.success(request, "Your examination has been submitted successfully.")
    return redirect('student_results')


@student_required
def request_retake(request, exam_id):
    """Allows students to submit a retest request maintained strictly by Super Admin."""
    exam = get_object_or_404(Exam, id=exam_id)
    assignment = get_object_or_404(ExamAssignment, exam=exam, student=request.user)

    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        if not reason:
            messages.error(request, "Please provide a reason for requesting a retake.")
            return redirect('student_results')

        # Check existing request
        from exams.models import ExamRetakeRequest
        existing = ExamRetakeRequest.objects.filter(exam=exam, student=request.user, status='PENDING').first()
        if existing:
            messages.warning(request, "You already have a pending retake request awaiting Super Admin authorization.")
        else:
            ExamRetakeRequest.objects.create(
                exam=exam,
                student=request.user,
                reason=reason,
                status='PENDING'
            )
            AuditLog.objects.create(
                user=request.user,
                action='RETAKE_REQUESTED',
                details=f"Student {request.user.username} submitted retake request for exam '{exam.title}'."
            )
            messages.success(request, "Your retake request has been submitted to the Super Admin. You will be able to retake the test once the Super Admin approves it.")
    return redirect('student_results')


@student_required
def student_results(request):
    """View personal published results with retake status and auto-repair for coding scores."""
    from exams.models import ExamRetakeRequest
    results = Result.objects.filter(student=request.user, is_published=True).select_related('exam', 'session')

    # Auto re-evaluate any coding exams that have 0 score or was evaluated incorrectly
    for r in results:
        exam = r.exam
        session = r.session
        if session:
            exam_questions = ExamQuestion.objects.filter(exam=exam).select_related('question')
            has_coding = any(eq.question.question_type == 'CODING' for eq in exam_questions)
            if has_coding and r.score == Decimal('0.0'):
                total_score = Decimal('0.0')
                correct_count = 0
                wrong_count = 0
                for eq in exam_questions:
                    q = eq.question
                    student_ans = StudentAnswer.objects.filter(session=session, question=q).first()
                    if q.question_type == 'CODING' and student_ans and student_ans.submitted_code:
                        marks, is_all, passed_t, tot_t = evaluate_coding_submission(student_ans.submitted_code, q, eq.marks)
                        student_ans.marks_obtained = marks
                        student_ans.is_evaluated = True
                        student_ans.save()
                        total_score += marks
                        if is_all or marks > 0:
                            correct_count += 1
                        else:
                            wrong_count += 1
                    elif q.question_type in ('MCQ_SINGLE', 'MCQ_MULTI') and student_ans and student_ans.selected_option_letter:
                        correct_opt = q.options.filter(is_correct=True).first()
                        if correct_opt and correct_opt.option_letter == student_ans.selected_option_letter:
                            total_score += Decimal(str(eq.marks))
                            correct_count += 1
                        else:
                            wrong_count += 1
                    else:
                        wrong_count += 1

                total_marks = Decimal(str(exam.total_marks or 100))
                pass_val = Decimal(str(exam.pass_marks or 0))
                pass_threshold = (pass_val / Decimal('100.0')) * total_marks if (pass_val > total_marks and total_marks > 0) else pass_val

                r.score = total_score
                r.percentage = ((total_score / total_marks) * 100).quantize(Decimal('0.01')) if total_marks > 0 else Decimal('0.0')
                r.correct_answers = correct_count
                r.wrong_answers = wrong_count
                r.is_passed = total_score >= pass_threshold
                r.save()
            elif r.is_passed == False:
                # Fix pass/fail threshold if pass_marks was entered as a percentage
                total_marks = Decimal(str(exam.total_marks or 100))
                pass_val = Decimal(str(exam.pass_marks or 0))
                pass_threshold = (pass_val / Decimal('100.0')) * total_marks if (pass_val > total_marks and total_marks > 0) else pass_val
                if r.score >= pass_threshold and r.score > 0:
                    r.is_passed = True
                    r.save()

    results_list = list(results)
    for r in results_list:
        if r.session and r.answers_approved:
            r.answers_list = list(
                StudentAnswer.objects.filter(session=r.session)
                .select_related('question')
                .prefetch_related('question__options')
                .order_by('question__id')
            )
        else:
            r.answers_list = []

    retake_requests = {r.exam_id: r for r in ExamRetakeRequest.objects.filter(student=request.user)}
    return render(request, 'student/results.html', {
        'results': results_list,
        'retake_requests': retake_requests
    })


@login_required
def download_qa_sheet_pdf(request, result_id):
    """
    Download student's official Question & Answer Sheet as a PDF document.
    Only accessible if the result is approved by the trainer or requested by admin/trainer.
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

    # Permission check: Student can only view their own approved result; Admin/Trainer can view any
    is_staff = request.user.role in ('ADMIN', 'SUPER_ADMIN', 'TRAINER') or request.user.is_superuser
    if not is_staff:
        if result.student != request.user:
            messages.error(request, "Permission denied.")
            return redirect('student_results')
        if not result.answers_approved:
            messages.error(request, "Your answer sheet has not yet been approved by the trainer.")
            return redirect('student_results')

    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, KeepTogether, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import inch

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

    meta_style = ParagraphStyle(
        'QAMeta',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#334155')
    )
    q_num_style = ParagraphStyle(
        'QANum',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13,
        textColor=colors.HexColor('#0f4c81')
    )
    q_text_style = ParagraphStyle(
        'QAText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#0f172a')
    )
    opt_style = ParagraphStyle(
        'QAOpt',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor('#334155')
    )
    opt_correct_style = ParagraphStyle(
        'QAOptCorrect',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor('#15803d')
    )
    opt_wrong_style = ParagraphStyle(
        'QAOptWrong',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor('#b91c1c')
    )
    badge_style = ParagraphStyle(
        'QABadge',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        alignment=2
    )

    # Header with Logo
    logo_path = os.path.join(settings.BASE_DIR, 'static', 'images', 'satx_logo.png')
    header_row = []
    if os.path.exists(logo_path):
        try:
            img = RLImage(logo_path, width=1.1*inch, height=0.85*inch)
            header_row.append(img)
        except Exception:
            header_row.append(Paragraph("<b>[SATX]</b>", meta_style))
    else:
        header_row.append(Paragraph("<b>SATX</b>", meta_style))

    brand_text = """
    <b><font size="12" color="#0a192f">SATX EXAM PORTAL</font></b><br/>
    <font color="#0f4c81" size="10"><b>OFFICIAL QUESTION &amp; ANSWER REVIEW SHEET</b></font><br/>
    <font color="#64748b" size="8">Candidate Performance Review &bull; Approved Academic Document</font><br/>
    <font color="#334155" size="8">Generated On: <b>{}</b> &bull; Candidate: <b>{} ({})</b></font>
    """.format(
        timezone.now().strftime('%d %B %Y, %I:%M %p'),
        result.student.get_full_name() or result.student.username,
        getattr(result.student, 'student_profile', None).reg_no if getattr(result.student, 'student_profile', None) else result.student.username
    )
    header_row.append(Paragraph(brand_text, meta_style))

    header_table = Table([header_row], colWidths=[1.0*inch, 6.4*inch])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(header_table)
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#0f4c81'), spaceAfter=8))

    # Candidate & Exam Info Summary
    exam = result.exam
    prof = getattr(result.student, 'student_profile', None)
    summary_data = [
        [
            Paragraph(f"<b>Exam:</b> {exam.title}", meta_style),
            Paragraph(f"<b>Course:</b> {exam.course.name if exam.course else 'N/A'}", meta_style),
            Paragraph(f"<b>Batch:</b> {prof.batch.name if prof and prof.batch else 'All Batches'}", meta_style),
        ],
        [
            Paragraph(f"<b>Total Score:</b> <b>{result.score} / {exam.total_marks}</b> ({result.percentage}%)", meta_style),
            Paragraph(f"<b>Correct / Total:</b> {result.correct_answers} / {result.total_questions}", meta_style),
            Paragraph(f"<b>Result:</b> <font color='{'#10b981' if result.is_passed else '#ef4444'}'><b>{'PASSED' if result.is_passed else 'FAILED'}</b></font>", meta_style),
        ]
    ]
    summary_table = Table(summary_data, colWidths=[2.5*inch, 2.5*inch, 2.4*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('PADDING', (0, 0), (-1, -1), 4),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 10))

    # Answers List
    answers = []
    if result.session:
        answers = (
            StudentAnswer.objects.filter(session=result.session)
            .select_related('question')
            .prefetch_related('question__options')
            .order_by('question__id')
        )

    for idx, ans in enumerate(answers, 1):
        q = ans.question
        score_color = '#15803d' if ans.marks_obtained > 0 else '#b91c1c'
        q_rows = []

        # Question title row with type and score
        q_head = [
            Paragraph(f"<b>Q{idx}. [{q.get_question_type_display()}]</b>", q_num_style),
            Paragraph(f"<font color='{score_color}'><b>{ans.marks_obtained} / {q.marks} Mark{'s' if q.marks != 1 else ''}</b></font>", badge_style)
        ]
        q_head_table = Table([q_head], colWidths=[5.4*inch, 2.0*inch])
        q_head_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 2),
        ]))
        q_rows.append([q_head_table])

        # Question Text
        escaped_q_text = q.question_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        q_rows.append([Paragraph(escaped_q_text, q_text_style)])

        # Question specific content
        if q.question_type in ('MCQ_SINGLE', 'MCQ_MULTI'):
            for opt in q.options.all():
                opt_txt = opt.option_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                is_selected = (opt.option_letter == ans.selected_option_letter)
                is_correct = opt.is_correct

                if is_selected and is_correct:
                    line = f"<b>[{opt.option_letter}]</b> {opt_txt} &nbsp; <font color='#15803d'><b>(Your Answer - Correct)</b></font>"
                    style = opt_correct_style
                elif is_selected and not is_correct:
                    line = f"<b>[{opt.option_letter}]</b> {opt_txt} &nbsp; <font color='#b91c1c'><b>(Your Answer)</b></font>"
                    style = opt_wrong_style
                elif is_correct:
                    line = f"<b>[{opt.option_letter}]</b> {opt_txt} &nbsp; <font color='#15803d'><b>(Correct Answer)</b></font>"
                    style = opt_correct_style
                else:
                    line = f"<b>[{opt.option_letter}]</b> {opt_txt}"
                    style = opt_style

                q_rows.append([Paragraph(line, style)])

        elif q.question_type == 'THEORY':
            ans_text = (ans.theory_answer or '(No answer submitted)').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            q_rows.append([Paragraph(f"<b>Candidate Answer:</b> {ans_text}", opt_style)])
            kws = (q.keywords or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            q_rows.append([Paragraph(f"<b>Required Key Word(s):</b> <font color='#0f4c81'><b>{kws}</b></font>", opt_style)])

        elif q.question_type == 'CODING':
            code_text = (ans.submitted_code or '# No code submitted').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            q_rows.append([Paragraph(f"<b>Submitted Code:</b><br/><font face='Courier' size='7'>{code_text[:500]}</font>", opt_style)])

        if q.explanation:
            exp_text = q.explanation.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            q_rows.append([Paragraph(f"<i>Explanation: {exp_text}</i>", meta_style)])

        q_table = Table(q_rows, colWidths=[7.4*inch])
        q_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#ffffff' if idx % 2 == 1 else '#f8fafc')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('PADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, 0), 4),
            ('BOTTOMPADDING', (0, -1), (-1, -1), 4),
        ]))
        elements.append(KeepTogether([q_table]))
        elements.append(Spacer(1, 6))

    elements.append(Spacer(1, 10))
    # Signatures
    sign_data = [
        [
            Paragraph("____________________________<br/><b>Verified By:</b><br/>Trainer / Examiner", meta_style),
            Paragraph("____________________________<br/><b>Official Approval:</b><br/>Branch Head / Admin", meta_style),
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

    filename = f"SATX_Answer_Sheet_{result.student.username}_{result.exam.id}.pdf"
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


