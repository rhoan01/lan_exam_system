import json
import random
import string

from django.contrib import messages
from django.db import transaction, IntegrityError
from django.db.models import F, Prefetch
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from accounts.decorators import student_required
from exams.models import Exam, Question, ImageIdentificationItem

from .grading import grade_answer
from .models import ExamAttempt, StudentAnswer, ExamAccessGrant


def _student_can_access(exam, user):
    """Require class eligibility, an enabled gate, and a current unlock."""
    profile = getattr(user, 'student_profile', None)
    if not profile or not exam.is_available_to_student(profile):
        return False
    if not exam.access_code_enabled or not exam.access_code:
        return False
    return ExamAccessGrant.objects.filter(student=user, exam=exam).exists()


@student_required
def student_dashboard(request):
    profile = getattr(request.user, 'student_profile', None)

    attempted_exam_ids = set(ExamAttempt.objects.filter(
        student=request.user, is_submitted=True
    ).values_list('exam_id', flat=True))
    granted_exam_ids = set(ExamAccessGrant.objects.filter(
        student=request.user
    ).values_list('exam_id', flat=True))

    candidate_exams = Exam.objects.filter(
        is_published=True, access_code_enabled=True, id__in=granted_exam_ids,
    ).exclude(
        id__in=attempted_exam_ids
    ).select_related('subject').prefetch_related('target_programs')

    available_exams = [
        exam for exam in candidate_exams
        if profile and exam.is_available_to_student(profile)
    ]

    completed_attempts = ExamAttempt.objects.filter(
        student=request.user, is_submitted=True
    ).select_related('exam', 'exam__subject').order_by('-submitted_at')

    return render(request, 'results/student_dashboard.html', {
        'available_exams': available_exams,
        'completed_attempts': completed_attempts,
    })


@student_required
def redeem_access_code(request):
    if request.method == 'POST':
        code = request.POST.get('access_code', '').strip().upper()
        if not code:
            messages.error(request, "Please enter an access code.")
            return redirect('results:student_dashboard')

        exam = Exam.objects.filter(
            access_code=code,
            access_code_enabled=True,
            is_published=True,
        ).first()
        if not exam:
            messages.error(
                request,
                "That code is invalid, has changed, is disabled, or the exam is not published.",
            )
            return redirect('results:student_dashboard')

        profile = getattr(request.user, 'student_profile', None)
        if not profile or not exam.is_available_to_student(profile):
            messages.error(
                request,
                "This exam is not assigned to your program, year level, and section.",
            )
            return redirect('results:student_dashboard')

        ExamAccessGrant.objects.get_or_create(student=request.user, exam=exam)
        messages.success(request, f"Access granted — '{exam.title}' is now on your dashboard.")
    return redirect('results:student_dashboard')


def _time_remaining_seconds(attempt):
    elapsed = (timezone.now() - attempt.started_at).total_seconds()
    total_allowed = attempt.exam.time_limit_minutes * 60 + attempt.extra_time_seconds
    return max(0, int(total_allowed - elapsed))


def _save_answers_from_post(exam, attempt, post_data):
    """Shared by autosave and final submission: writes whatever answers are
    present in post_data for this exam's questions, without grading. Only
    writes fields that actually changed, to keep autosave cheap when called
    frequently."""
    student_image_items = Prefetch(
        'image_identification_items',
        queryset=ImageIdentificationItem.objects.only('id', 'question_id', 'number'),
        to_attr='student_image_items',
    )
    questions = list(exam.questions.prefetch_related(
        'choices', 'matching_pairs', student_image_items,
    ))
    existing_answers = {a.question_id: a for a in attempt.answers.all()}

    to_create = []
    to_update = []

    for question in questions:
        field_name = f'question_{question.id}'
        selected_choice = None
        text_answer = ''

        if question.question_type in (Question.MCQ, Question.PROGRAMMING_MCQ, Question.TF):
            choice_id = post_data.get(field_name)
            if choice_id:
                for c in question.choices.all():
                    if str(c.id) == choice_id:
                        selected_choice = c
                        break
        elif question.question_type == Question.MATCH:
            # One dropdown per Column A row - collect them into a
            # {pair_id: chosen_column_b_text} JSON mapping.
            answer_map = {}
            for pair in question.matching_pairs.all():
                value = post_data.get(f'{field_name}_pair_{pair.id}', '').strip()
                if value:
                    answer_map[str(pair.id)] = value
            text_answer = json.dumps(answer_map)
        elif question.question_type == Question.IMAGE_IDENTIFICATION:
            answer_map = {}
            for item in question.student_image_items:
                value = post_data.get(f'{field_name}_item_{item.number}', '').strip()
                if value:
                    answer_map[str(item.number)] = value
            text_answer = json.dumps(answer_map)
        else:
            text_answer = post_data.get(field_name, '')

        existing = existing_answers.get(question.id)
        if existing:
            new_choice_id = selected_choice.id if selected_choice else None
            if existing.selected_choice_id != new_choice_id or existing.text_answer != text_answer:
                existing.selected_choice = selected_choice
                existing.text_answer = text_answer
                to_update.append(existing)
        else:
            to_create.append(StudentAnswer(
                attempt=attempt, question=question,
                selected_choice=selected_choice, text_answer=text_answer,
            ))

    if to_create:
        StudentAnswer.objects.bulk_create(to_create)
    if to_update:
        StudentAnswer.objects.bulk_update(to_update, ['selected_choice', 'text_answer'])


def _auto_grade_and_submit(attempt):
    """Grades whatever answers exist for this attempt and marks it submitted.

    Written to use a small, fixed number of queries regardless of how many
    questions the exam has (important when hundreds of students may submit
    at the same time): one query for questions, one for existing answers
    (with their selected choice preloaded), one bulk_update for the graded
    answers, and one save for the attempt itself.
    """
    questions = list(attempt.exam.questions.prefetch_related('image_identification_items'))
    total_points = sum(q.points for q in questions)

    answers_by_qid = {a.question_id: a for a in attempt.answers.select_related('selected_choice')}

    total_score = 0
    graded_answers = []
    for question in questions:
        answer = answers_by_qid.get(question.id)
        if not answer:
            continue
        points, needs_review = grade_answer(
            question, selected_choice=answer.selected_choice, text_answer=answer.text_answer
        )
        answer.points_earned = points
        answer.needs_manual_review = needs_review
        graded_answers.append(answer)
        total_score += points

    if graded_answers:
        StudentAnswer.objects.bulk_update(graded_answers, ['points_earned', 'needs_manual_review'])

    attempt.score = round(total_score)
    attempt.total_points = total_points
    attempt.is_submitted = True
    attempt.submitted_at = timezone.now()
    attempt.save(update_fields=['score', 'total_points', 'is_submitted', 'submitted_at'])


@student_required
def take_exam(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id, is_published=True)

    if not _student_can_access(exam, request.user):
        messages.error(
            request,
            "This exam isn't available to your year level. If you were given an "
            "access code, enter it on your dashboard to unlock it."
        )
        return redirect('results:student_dashboard')

    # get_or_create isn't fully race-proof under heavy concurrency (many
    # students hitting "Start" for the same exam at once is fine since each
    # is keyed by student+exam, but a double-submitted request from the same
    # student, e.g. a doubled click, can still race). The unique_together
    # constraint on ExamAttempt guarantees correctness at the DB level; if a
    # collision happens we simply re-fetch the row that "won".
    try:
        attempt, created = ExamAttempt.objects.get_or_create(student=request.user, exam=exam)
    except IntegrityError:
        attempt = ExamAttempt.objects.get(student=request.user, exam=exam)

    if attempt.is_submitted:
        return redirect('results:attempt_result', attempt_id=attempt.id)

    remaining_seconds = _time_remaining_seconds(attempt)
    if remaining_seconds <= 0:
        _auto_grade_and_submit(attempt)
        messages.info(request, "Time was already up for this exam; it has been auto-submitted.")
        return redirect('results:attempt_result', attempt_id=attempt.id)

    student_image_items = Prefetch(
        'image_identification_items',
        queryset=ImageIdentificationItem.objects.only('id', 'question_id', 'number'),
        to_attr='student_image_items',
    )
    questions = list(exam.questions.prefetch_related(
        'choices', 'matching_pairs', 'matching_distractors', student_image_items,
    ))

    # Randomize order deterministically per attempt (seeded on the attempt's
    # own id), so each student sees a consistent, stable order across
    # reloads/resumes, but different students see different orders - this is
    # what actually deters copying between adjacent students, and it doesn't
    # affect grading at all since answers are always matched by question/
    # choice ID, never by position.
    if exam.shuffle_questions:
        random.Random(attempt.id).shuffle(questions)

    existing_answers = {a.question_id: a for a in attempt.answers.all()}

    for q in questions:
        existing = existing_answers.get(q.id)
        q.saved_choice_id = existing.selected_choice_id if existing else None
        q.saved_text = existing.text_answer if existing else ''

        if q.question_type in (Question.MCQ, Question.PROGRAMMING_MCQ, Question.TF):
            choice_list = list(q.choices.all())
            if exam.shuffle_choices:
                random.Random(f'{attempt.id}-{q.id}').shuffle(choice_list)
            q.shuffled_choices = choice_list

        elif q.question_type == Question.MATCH:
            pool = q.column_b_pool()
            if exam.shuffle_choices:
                random.Random(f'{attempt.id}-{q.id}-match').shuffle(pool)
            q.column_b_options = list(zip(string.ascii_uppercase, pool))

            saved_map = {}
            if existing and existing.text_answer:
                try:
                    parsed = json.loads(existing.text_answer)
                    if isinstance(parsed, dict):
                        saved_map = parsed
                except (ValueError, TypeError):
                    saved_map = {}
            q.matching_rows = [
                (pair, saved_map.get(str(pair.id), '')) for pair in q.matching_pairs.all()
            ]

        elif q.question_type == Question.IMAGE_IDENTIFICATION:
            saved_map = {}
            if existing and existing.text_answer:
                try:
                    parsed = json.loads(existing.text_answer)
                    if isinstance(parsed, dict):
                        saved_map = parsed
                except (ValueError, TypeError):
                    saved_map = {}
            q.image_identification_rows = [
                (item.number, saved_map.get(str(item.number), ''))
                for item in q.student_image_items
            ]

    # Resume on the same item the student had open before - whether that's
    # from a normal reload, a power/network interruption, or an instructor
    # re-opening an accidentally-submitted attempt.
    resume_index = attempt.current_question_index
    if resume_index >= len(questions):
        resume_index = 0

    return render(request, 'results/take_exam.html', {
        'exam': exam,
        'attempt': attempt,
        'questions': questions,
        'remaining_seconds': remaining_seconds,
        'resume_index': resume_index,
    })


@student_required
def autosave_exam(request, exam_id):
    """Called periodically (and on every answer change) from the exam page
    so that a sudden power/network interruption never loses more than a few
    seconds of work. Saves answers and the student's current question
    position, but never grades or marks the attempt submitted."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'POST required'}, status=405)

    exam = get_object_or_404(Exam, id=exam_id, is_published=True)

    if not _student_can_access(exam, request.user):
        return JsonResponse({'status': 'error', 'message': 'not accessible'}, status=403)

    try:
        attempt = ExamAttempt.objects.get(student=request.user, exam=exam)
    except ExamAttempt.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'no attempt in progress'}, status=404)

    if attempt.is_submitted:
        return JsonResponse({'status': 'already_submitted'})

    remaining_seconds = _time_remaining_seconds(attempt)
    if remaining_seconds <= 0:
        _auto_grade_and_submit(attempt)
        return JsonResponse({'status': 'time_up'})

    _save_answers_from_post(exam, attempt, request.POST)

    current_index = request.POST.get('current_index')
    if current_index is not None and current_index.isdigit():
        new_index = int(current_index)
        if new_index != attempt.current_question_index:
            attempt.current_question_index = new_index
            attempt.save(update_fields=['current_question_index'])

    return JsonResponse({'status': 'ok', 'remaining_seconds': remaining_seconds})


@student_required
def submit_exam(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id, is_published=True)

    if not _student_can_access(exam, request.user):
        messages.error(request, "This exam isn't available to you.")
        return redirect('results:student_dashboard')

    if request.method != 'POST':
        return redirect('results:take_exam', exam_id=exam.id)

    with transaction.atomic():
        # select_for_update locks this student's attempt row for the
        # duration of the transaction, so a duplicate/near-simultaneous
        # submit (e.g. the timer firing at the same instant as a manual
        # click) can't grade the same attempt twice or interleave writes.
        attempt = get_object_or_404(
            ExamAttempt.objects.select_for_update(), student=request.user, exam=exam
        )

        if attempt.is_submitted:
            return redirect('results:attempt_result', attempt_id=attempt.id)

        # Even if the timer already ran out client-side, don't trust the
        # client: re-check server-side before accepting answers.
        if _time_remaining_seconds(attempt) <= 0:
            _auto_grade_and_submit(attempt)
            return redirect('results:attempt_result', attempt_id=attempt.id)

        _save_answers_from_post(exam, attempt, request.POST)
        _auto_grade_and_submit(attempt)

    messages.success(request, "Exam submitted successfully!")
    return redirect('results:attempt_result', attempt_id=attempt.id)


@student_required
def attempt_result(request, attempt_id):
    attempt = get_object_or_404(ExamAttempt, id=attempt_id, student=request.user, is_submitted=True)
    answers = attempt.answers.select_related('question').order_by('question__order')
    return render(request, 'results/attempt_result.html', {'attempt': attempt, 'answers': answers})


@student_required
def log_tab_switch(request, exam_id):
    """Called via fetch() from the exam page whenever the student switches
    away from the tab/window. Fire-and-forget: failures here should never
    block the student's exam, so this always returns a plain JSON OK."""
    if request.method == 'POST':
        ExamAttempt.objects.filter(
            student=request.user, exam_id=exam_id, is_submitted=False
        ).update(tab_switch_count=F('tab_switch_count') + 1)
    return JsonResponse({'status': 'ok'})
