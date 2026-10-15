import csv
import re

from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone

from accounts.decorators import instructor_required
from results.models import ExamAttempt
from results.grading import parse_matching_answer
from .forms import (
    SubjectForm, ExamForm, QuestionForm, QuestionEditForm, ChoiceFormSet, AnswerKeyForm,
    BulkImportForm, MatchingPairFormSet, MatchingDistractorForm,
)
from .models import Subject, Exam, Question, Choice, AnswerKey, MatchingPair, MatchingDistractor, MAX_ITEMS_PER_EXAM
from .parsing import parse_bulk_questions, BulkImportError


@instructor_required
def instructor_dashboard(request):
    subjects = Subject.objects.filter(instructor=request.user)
    return render(request, 'exams/instructor_dashboard.html', {'subjects': subjects})


@instructor_required
def subject_create(request):
    if request.method == 'POST':
        form = SubjectForm(request.POST)
        if form.is_valid():
            subject = form.save(commit=False)
            subject.instructor = request.user
            subject.save()
            messages.success(request, f"Subject '{subject.name}' created.")
            return redirect('exams:instructor_dashboard')
    else:
        form = SubjectForm()
    return render(request, 'exams/subject_form.html', {'form': form})


@instructor_required
def subject_detail(request, subject_id):
    subject = get_object_or_404(Subject, id=subject_id, instructor=request.user)
    exams = subject.exams.all()
    return render(request, 'exams/subject_detail.html', {'subject': subject, 'exams': exams})


@instructor_required
def subject_delete(request, subject_id):
    subject = get_object_or_404(Subject, id=subject_id, instructor=request.user)
    if request.method == 'POST':
        confirmation = request.POST.get('confirm_name', '').strip()
        if confirmation != subject.code:
            messages.error(request, "The code you typed didn't match — subject was not deleted.")
            return redirect('exams:subject_delete_confirm', subject_id=subject.id)
        title = f"{subject.code} - {subject.name}"
        subject.delete()
        messages.success(request, f"Subject '{title}' and all of its exams, questions, and results have been deleted.")
        return redirect('exams:instructor_dashboard')
    return redirect('exams:subject_delete_confirm', subject_id=subject.id)


@instructor_required
def subject_delete_confirm(request, subject_id):
    subject = get_object_or_404(Subject, id=subject_id, instructor=request.user)
    exam_count = subject.exams.count()
    attempt_count = ExamAttempt.objects.filter(exam__subject=subject, is_submitted=True).count()
    return render(request, 'exams/subject_delete_confirm.html', {
        'subject': subject, 'exam_count': exam_count, 'attempt_count': attempt_count,
    })


@instructor_required
def exam_create(request, subject_id):
    subject = get_object_or_404(Subject, id=subject_id, instructor=request.user)
    if request.method == 'POST':
        form = ExamForm(request.POST)
        if form.is_valid():
            exam = form.save(commit=False)
            exam.subject = subject
            exam.save()
            messages.success(request, f"Exam '{exam.title}' created. Now add questions (up to {MAX_ITEMS_PER_EXAM}).")
            return redirect('exams:exam_detail', exam_id=exam.id)
    else:
        form = ExamForm()
    return render(request, 'exams/exam_form.html', {'form': form, 'subject': subject})


@instructor_required
def exam_edit(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id, subject__instructor=request.user)
    if request.method == 'POST':
        form = ExamForm(request.POST, instance=exam)
        if form.is_valid():
            form.save()
            messages.success(request, "Exam settings updated.")
            return redirect('exams:exam_detail', exam_id=exam.id)
    else:
        form = ExamForm(instance=exam)
    return render(request, 'exams/exam_form.html', {'form': form, 'subject': exam.subject, 'exam': exam})


@instructor_required
def exam_detail(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id, subject__instructor=request.user)
    questions = exam.questions.all()
    return render(request, 'exams/exam_detail.html', {
        'exam': exam,
        'questions': questions,
        'max_items': MAX_ITEMS_PER_EXAM,
    })


@instructor_required
def exam_toggle_publish(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id, subject__instructor=request.user)
    if exam.total_items() == 0:
        messages.error(request, "Add at least one question before publishing.")
    else:
        exam.is_published = not exam.is_published
        if exam.is_published and not exam.access_code:
            exam.access_code = exam.generate_access_code()
        exam.save()
        messages.success(request, f"Exam is now {'published' if exam.is_published else 'unpublished'}.")
    return redirect('exams:exam_detail', exam_id=exam.id)


@instructor_required
def exam_delete(request, exam_id):
    """Permanently deletes an exam - published or not - along with all of
    its questions, answer keys, and every student's results for it."""
    exam = get_object_or_404(Exam, id=exam_id, subject__instructor=request.user)
    subject_id = exam.subject_id
    if request.method == 'POST':
        title = exam.title
        exam.delete()
        messages.success(request, f"Exam '{title}' and all of its questions/results have been deleted.")
        return redirect('exams:subject_detail', subject_id=subject_id)
    return redirect('exams:exam_detail', exam_id=exam.id)


@instructor_required
def question_create(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id, subject__instructor=request.user)

    if not exam.has_room_for_more_questions():
        messages.error(request, f"This exam already has the maximum of {MAX_ITEMS_PER_EXAM} items.")
        return redirect('exams:exam_detail', exam_id=exam.id)

    if request.method == 'POST':
        form = QuestionForm(request.POST)
        choice_formset = ChoiceFormSet(request.POST)
        key_form = AnswerKeyForm(request.POST)
        pair_formset = MatchingPairFormSet(request.POST, instance=Question())
        distractor_form = MatchingDistractorForm(request.POST)

        if form.is_valid():
            qtype = form.cleaned_data['question_type']
            valid_extra = True

            if qtype == Question.MCQ:
                choice_formset_bound = ChoiceFormSet(request.POST, instance=Question())
                valid_extra = choice_formset_bound.is_valid() and any(
                    f.cleaned_data.get('choice_text') for f in choice_formset_bound.forms if f.cleaned_data
                )
                if not valid_extra:
                    messages.error(request, "Please provide at least one answer choice.")

            elif qtype == Question.TF:
                tf_answer = request.POST.get('tf_correct_answer')
                valid_extra = tf_answer in ('True', 'False')
                if not valid_extra:
                    messages.error(request, "Please select whether True or False is the correct answer.")

            elif qtype == Question.MATCH:
                valid_pairs = pair_formset.is_valid() and sum(
                    1 for f in pair_formset.forms
                    if f.cleaned_data and not f.cleaned_data.get('DELETE')
                    and f.cleaned_data.get('left_text') and f.cleaned_data.get('right_text')
                ) >= 2
                valid_extra = valid_pairs and distractor_form.is_valid()
                if not valid_extra:
                    messages.error(request, "Matching questions need at least 2 complete Column A/B pairs.")

            else:
                valid_extra = key_form.is_valid() and key_form.cleaned_data.get('correct_answers', '').strip()
                if not valid_extra:
                    messages.error(request, "Please provide an answer key for this question.")

            if valid_extra:
                question = form.save(commit=False)
                question.exam = exam
                question.order = exam.total_items() + 1
                question.save()

                if qtype == Question.MCQ:
                    formset = ChoiceFormSet(request.POST, instance=question)
                    formset.is_valid()
                    formset.save()
                    if not any(c.is_correct for c in question.choices.all()):
                        messages.warning(request, "Note: no choice was marked correct for that question.")
                    messages.success(request, "Multiple choice question added.")

                elif qtype == Question.TF:
                    tf_answer = request.POST.get('tf_correct_answer')
                    Choice.objects.create(question=question, choice_text='True', is_correct=(tf_answer == 'True'))
                    Choice.objects.create(question=question, choice_text='False', is_correct=(tf_answer == 'False'))
                    messages.success(request, "True/False question added.")

                elif qtype == Question.MATCH:
                    formset = MatchingPairFormSet(request.POST, instance=question)
                    formset.is_valid()
                    pairs = formset.save(commit=False)
                    for i, pair in enumerate(pairs, start=1):
                        pair.question = question
                        pair.order = i
                        pair.save()
                    for deleted in formset.deleted_objects:
                        deleted.delete()

                    dform = MatchingDistractorForm(request.POST)
                    dform.is_valid()
                    for line in dform.cleaned_data.get('distractors_text', '').splitlines():
                        line = line.strip()
                        if line:
                            MatchingDistractor.objects.create(question=question, text=line)
                    messages.success(request, "Matching question added.")

                else:
                    key = key_form.save(commit=False)
                    key.question = question
                    key.save()
                    messages.success(request, "Question added with answer key.")
                return redirect('exams:exam_detail', exam_id=exam.id)
    else:
        form = QuestionForm(initial={'question_type': Question.MCQ, 'points': 1, 'expected_answer_count': 1})
        choice_formset = ChoiceFormSet()
        key_form = AnswerKeyForm()
        pair_formset = MatchingPairFormSet()
        distractor_form = MatchingDistractorForm()

    return render(request, 'exams/question_form.html', {
        'exam': exam,
        'form': form,
        'choice_formset': choice_formset,
        'key_form': key_form,
        'pair_formset': pair_formset,
        'distractor_form': distractor_form,
        'question_types': Question.TYPE_CHOICES,
    })


@instructor_required
def question_edit(request, question_id):
    """Edit an existing question's text/points/choices/answer key. The
    question TYPE itself is fixed once created - switching types would
    orphan existing choices or answer keys, so that isn't offered here."""
    question = get_object_or_404(Question, id=question_id, exam__subject__instructor=request.user)
    exam = question.exam
    qtype = question.question_type

    existing_key = getattr(question, 'answer_key', None)
    tf_current_answer = None
    if qtype == Question.TF:
        correct = next((c for c in question.choices.all() if c.is_correct), None)
        tf_current_answer = correct.choice_text if correct else None

    existing_distractors_text = ''
    if qtype == Question.MATCH:
        existing_distractors_text = '\n'.join(d.text for d in question.matching_distractors.all())

    if request.method == 'POST':
        form = QuestionEditForm(request.POST, instance=question)
        choice_formset = ChoiceFormSet(request.POST, instance=question)
        key_form = AnswerKeyForm(request.POST, instance=existing_key)
        pair_formset = MatchingPairFormSet(request.POST, instance=question)
        distractor_form = MatchingDistractorForm(request.POST)

        if form.is_valid():
            valid_extra = True

            if qtype == Question.MCQ:
                valid_extra = choice_formset.is_valid() and any(
                    f.cleaned_data.get('choice_text') for f in choice_formset.forms
                    if f.cleaned_data and not f.cleaned_data.get('DELETE')
                )
                if not valid_extra:
                    messages.error(request, "Please provide at least one answer choice.")

            elif qtype == Question.TF:
                tf_answer = request.POST.get('tf_correct_answer')
                valid_extra = tf_answer in ('True', 'False')
                if not valid_extra:
                    messages.error(request, "Please select whether True or False is the correct answer.")

            elif qtype == Question.MATCH:
                valid_pairs = pair_formset.is_valid() and sum(
                    1 for f in pair_formset.forms
                    if f.cleaned_data and not f.cleaned_data.get('DELETE')
                    and f.cleaned_data.get('left_text') and f.cleaned_data.get('right_text')
                ) >= 2
                valid_extra = valid_pairs and distractor_form.is_valid()
                if not valid_extra:
                    messages.error(request, "Matching questions need at least 2 complete Column A/B pairs.")

            else:
                valid_extra = key_form.is_valid() and key_form.cleaned_data.get('correct_answers', '').strip()
                if not valid_extra:
                    messages.error(request, "Please provide an answer key for this question.")

            if valid_extra:
                form.save()

                if qtype == Question.MCQ:
                    choice_formset.save()
                    if not any(c.is_correct for c in question.choices.all()):
                        messages.warning(request, "Note: no choice is marked correct for that question.")
                    messages.success(request, "Question updated.")

                elif qtype == Question.TF:
                    tf_answer = request.POST.get('tf_correct_answer')
                    for choice in question.choices.all():
                        choice.is_correct = (choice.choice_text == tf_answer)
                        choice.save(update_fields=['is_correct'])
                    messages.success(request, "Question updated.")

                elif qtype == Question.MATCH:
                    pairs = pair_formset.save(commit=False)
                    for i, pair in enumerate(pairs, start=1):
                        pair.question = question
                        pair.order = i
                        pair.save()
                    for deleted in pair_formset.deleted_objects:
                        deleted.delete()

                    # Replace the distractor list wholesale - simpler and
                    # safer than trying to diff a plain textarea against
                    # existing rows.
                    question.matching_distractors.all().delete()
                    for line in distractor_form.cleaned_data.get('distractors_text', '').splitlines():
                        line = line.strip()
                        if line:
                            MatchingDistractor.objects.create(question=question, text=line)
                    messages.success(request, "Question updated.")

                else:
                    key = key_form.save(commit=False)
                    key.question = question
                    key.save()
                    messages.success(request, "Question updated.")

                return redirect('exams:exam_detail', exam_id=exam.id)
    else:
        form = QuestionEditForm(instance=question)
        choice_formset = ChoiceFormSet(instance=question) if qtype == Question.MCQ else ChoiceFormSet()
        key_form = AnswerKeyForm(instance=existing_key)
        pair_formset = MatchingPairFormSet(instance=question) if qtype == Question.MATCH else MatchingPairFormSet()
        distractor_form = MatchingDistractorForm(initial={'distractors_text': existing_distractors_text})

    return render(request, 'exams/question_edit_form.html', {
        'exam': exam,
        'question': question,
        'form': form,
        'choice_formset': choice_formset,
        'key_form': key_form,
        'pair_formset': pair_formset,
        'distractor_form': distractor_form,
        'tf_current_answer': tf_current_answer,
    })


@instructor_required
def bulk_import_questions(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id, subject__instructor=request.user)
    remaining_slots = MAX_ITEMS_PER_EXAM - exam.total_items()

    if request.method == 'POST':
        form = BulkImportForm(request.POST, request.FILES)
        if form.is_valid():
            raw_text = form.cleaned_data.get('questions_text', '') or ''
            uploaded_file = form.cleaned_data.get('file')
            replace_existing = form.cleaned_data.get('replace_existing')

            if uploaded_file:
                try:
                    raw_text = uploaded_file.read().decode('utf-8')
                except UnicodeDecodeError:
                    messages.error(
                        request,
                        "Could not read that file. Please save it as plain text "
                        "(.txt, UTF-8 encoding) from Notepad and try again."
                    )
                    return render(request, 'exams/bulk_import.html', {
                        'exam': exam, 'form': form, 'remaining_slots': remaining_slots,
                    })

            # Replacing wipes existing questions first, so the full 100-item
            # budget is available regardless of what's there now.
            effective_slots = MAX_ITEMS_PER_EXAM if replace_existing else remaining_slots

            if effective_slots <= 0:
                messages.error(request, f"This exam already has the maximum of {MAX_ITEMS_PER_EXAM} items.")
                return redirect('exams:exam_detail', exam_id=exam.id)

            try:
                parsed = parse_bulk_questions(raw_text, effective_slots)
            except BulkImportError as e:
                messages.error(request, e.message)
            else:
                with transaction.atomic():
                    if replace_existing:
                        exam.questions.all().delete()
                        start_order = 1
                    else:
                        start_order = exam.total_items() + 1

                    for i, q in enumerate(parsed):
                        question = Question.objects.create(
                            exam=exam,
                            order=start_order + i,
                            question_type=q['question_type'],
                            question_text=q['question_text'],
                            points=q['points'],
                            expected_answer_count=q['expected_answer_count'],
                        )
                        if q['question_type'] in (Question.MCQ, Question.TF):
                            for choice_text, is_correct in q['choices']:
                                Choice.objects.create(
                                    question=question, choice_text=choice_text, is_correct=is_correct,
                                )
                        elif q['question_type'] == Question.MATCH:
                            for pair_order, (left_text, right_text) in enumerate(q['pairs'], start=1):
                                MatchingPair.objects.create(
                                    question=question, order=pair_order,
                                    left_text=left_text, right_text=right_text,
                                )
                            for distractor_text in q['distractors']:
                                MatchingDistractor.objects.create(question=question, text=distractor_text)
                        else:
                            AnswerKey.objects.create(
                                question=question, correct_answers='\n'.join(q['keys']),
                            )

                if replace_existing:
                    messages.success(
                        request,
                        f"Replaced all existing questions - imported {len(parsed)} new question(s)."
                    )
                else:
                    messages.success(request, f"Imported {len(parsed)} question(s) successfully.")
                return redirect('exams:exam_detail', exam_id=exam.id)
    else:
        form = BulkImportForm()

    return render(request, 'exams/bulk_import.html', {
        'exam': exam, 'form': form, 'remaining_slots': remaining_slots,
    })


@instructor_required
def question_delete(request, question_id):
    question = get_object_or_404(Question, id=question_id, exam__subject__instructor=request.user)
    exam_id = question.exam_id
    question.delete()
    # re-sequence order numbers
    for i, q in enumerate(Question.objects.filter(exam_id=exam_id).order_by('order', 'id'), start=1):
        if q.order != i:
            q.order = i
            q.save(update_fields=['order'])
    messages.success(request, "Question removed.")
    return redirect('exams:exam_detail', exam_id=exam_id)


def _group_attempts_by_section(attempts):
    """Groups an already-fetched list of attempts into
    [(section, [attempts...]), ...], preserving the relative order the
    attempts were given in and sorting sections alphabetically
    ('Unassigned' students last)."""
    buckets = {}
    for attempt in attempts:
        profile = getattr(attempt.student, 'student_profile', None)
        section = profile.section if profile else 'Unassigned'
        buckets.setdefault(section, []).append(attempt)
    return sorted(buckets.items(), key=lambda item: (item[0] == 'Unassigned', item[0]))


@instructor_required
def exam_results(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id, subject__instructor=request.user)
    attempts = list(ExamAttempt.objects.filter(exam=exam, is_submitted=True).select_related(
        'student', 'student__student_profile'
    ).order_by('-score'))
    in_progress_attempts = list(ExamAttempt.objects.filter(exam=exam, is_submitted=False).select_related(
        'student', 'student__student_profile'
    ).order_by('student__student_profile__id_number'))
    return render(request, 'exams/exam_results.html', {
        'exam': exam,
        'attempts': attempts,
        'in_progress_attempts': in_progress_attempts,
        'grouped_attempts': _group_attempts_by_section(attempts),
        'grouped_in_progress': _group_attempts_by_section(in_progress_attempts),
    })


@instructor_required
def view_student_attempt(request, attempt_id):
    """Shows the instructor exactly what a specific student answered on a
    submitted exam, question by question, alongside the correct answer/key
    for reference."""
    attempt = get_object_or_404(
        ExamAttempt, id=attempt_id, exam__subject__instructor=request.user, is_submitted=True
    )
    answers = attempt.answers.select_related(
        'question', 'selected_choice'
    ).prefetch_related('question__choices', 'question__matching_pairs').order_by('question__order')

    for answer in answers:
        question = answer.question
        if question.is_choice_based():
            correct_choice = next((c for c in question.choices.all() if c.is_correct), None)
            answer.correct_display = correct_choice.choice_text if correct_choice else '—'
            answer.student_display = answer.selected_choice.choice_text if answer.selected_choice else '(no answer)'
        elif question.question_type == Question.MATCH:
            submitted = parse_matching_answer(answer.text_answer)
            pairs = list(question.matching_pairs.all())
            answer.correct_display = '\n'.join(f"{p.left_text} → {p.right_text}" for p in pairs) or '—'
            if pairs:
                answer.student_display = '\n'.join(
                    f"{p.left_text} → {submitted.get(str(p.id)) or '(no answer)'}" for p in pairs
                )
            else:
                answer.student_display = '(no answer)'
        else:
            answer.correct_display = answer.question.answer_key.correct_answers if hasattr(question, 'answer_key') else '—'
            answer.student_display = answer.text_answer or '(no answer)'

    return render(request, 'exams/view_student_attempt.html', {'attempt': attempt, 'answers': answers})


@instructor_required
def export_exam_results_csv(request, exam_id):
    """Downloads a CSV report of every submitted attempt for this exam -
    student info, score, percentage, tab-switch count, and submission time.
    Grouped by section (with a blank/header row between each) and
    alphabetical by student name within each section. Opens directly in
    Excel or Google Sheets."""
    exam = get_object_or_404(Exam, id=exam_id, subject__instructor=request.user)
    attempts = ExamAttempt.objects.filter(exam=exam, is_submitted=True).select_related(
        'student', 'student__student_profile'
    ).order_by('student__student_profile__section', 'student__student_profile__full_name')

    response = HttpResponse(content_type='text/csv')
    safe_title = re.sub(r'[^A-Za-z0-9_-]+', '_', f"{exam.subject.code}_{exam.title}").strip('_')
    response['Content-Disposition'] = f'attachment; filename="{safe_title}_results.csv"'

    writer = csv.writer(response)
    header = [
        'Subject Code', 'Subject Name', 'Exam Title',
        'Student Name', 'ID Number', 'Course', 'Year Level', 'Section',
        'Score', 'Total Points', 'Percentage', 'Tab Switches', 'Submitted At',
    ]
    writer.writerow(header)

    grouped = _group_attempts_by_section(attempts)
    for i, (section, section_attempts) in enumerate(grouped):
        if i > 0:
            writer.writerow([])  # blank row between sections for readability
        writer.writerow([f"Section {section}"])
        for attempt in section_attempts:
            profile = getattr(attempt.student, 'student_profile', None)
            writer.writerow([
                exam.subject.code,
                exam.subject.name,
                exam.title,
                attempt.student.get_full_name(),
                profile.id_number if profile else '',
                profile.course if profile else '',
                profile.year_level if profile else '',
                profile.section if profile else '',
                int(attempt.score),
                int(attempt.total_points),
                attempt.percentage(),
                attempt.tab_switch_count,
                attempt.submitted_at.strftime('%Y-%m-%d %H:%M:%S') if attempt.submitted_at else '',
            ])

    return response


@instructor_required
def export_exam_results_pdf(request, exam_id):
    """Downloads a formatted PDF report of every submitted attempt for this
    exam - a summary block (submission count, average/highest/lowest score)
    followed by one results table per section, alphabetical by student name
    within each section, ready to print or archive."""
    from io import BytesIO

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    )

    exam = get_object_or_404(Exam, id=exam_id, subject__instructor=request.user)
    attempts = list(ExamAttempt.objects.filter(exam=exam, is_submitted=True).select_related(
        'student', 'student__student_profile'
    ).order_by('student__student_profile__section', 'student__student_profile__full_name'))

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(letter),
        leftMargin=0.5 * inch, rightMargin=0.5 * inch,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
        title=f"{exam.title} - Results Report",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'ReportTitle', parent=styles['Heading1'], fontSize=16, spaceAfter=2,
    )
    subtitle_style = ParagraphStyle(
        'ReportSubtitle', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#555555'),
    )
    section_style = ParagraphStyle(
        'SectionHeading', parent=styles['Heading2'], fontSize=12, spaceBefore=10, spaceAfter=6,
    )

    elements = [
        Paragraph(f"{exam.subject.code} — {exam.subject.name}", title_style),
        Paragraph(f"{exam.title} — Exam Results Report", subtitle_style),
        Paragraph(
            f"Total possible points: {exam.total_points()} &nbsp;|&nbsp; "
            f"Generated: {timezone.now().strftime('%B %d, %Y %I:%M %p')}",
            subtitle_style,
        ),
        Spacer(1, 0.15 * inch),
    ]

    if attempts:
        scores = [a.percentage() for a in attempts]
        summary_data = [
            ['Students Submitted', 'Average Score', 'Highest Score', 'Lowest Score'],
            [
                str(len(attempts)),
                f"{round(sum(scores) / len(scores))}%",
                f"{max(scores)}%",
                f"{min(scores)}%",
            ],
        ]
        summary_table = Table(summary_data, colWidths=[2.3 * inch] * 4)
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e4d8b')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#eef2f7')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dbe1e8')),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 0.25 * inch))

        col_widths = [1.9, 1.1, 1.5, 0.8, 1.0, 0.6, 0.7, 1.6]
        col_widths = [w * inch for w in col_widths]

        for section, section_attempts in _group_attempts_by_section(attempts):
            elements.append(Paragraph(f"Section {section}", section_style))

            table_data = [[
                'Student Name', 'ID Number', 'Course', 'Year',
                'Score', '%', 'Tab\nSwitches', 'Submitted At',
            ]]
            for attempt in section_attempts:
                profile = getattr(attempt.student, 'student_profile', None)
                table_data.append([
                    attempt.student.get_full_name(),
                    profile.id_number if profile else '',
                    profile.course if profile else '',
                    profile.year_level if profile else '',
                    f"{int(attempt.score)}/{int(attempt.total_points)}",
                    f"{attempt.percentage()}%",
                    str(attempt.tab_switch_count),
                    attempt.submitted_at.strftime('%b %d, %Y %I:%M %p') if attempt.submitted_at else '',
                ])

            results_table = Table(table_data, colWidths=col_widths, repeatRows=1)
            table_style = [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e4d8b')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('ALIGN', (4, 0), (6, -1), 'CENTER'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dbe1e8')),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]
            # Zebra-striped rows for readability across many students.
            for row_index in range(1, len(table_data)):
                if row_index % 2 == 0:
                    table_style.append(('BACKGROUND', (0, row_index), (-1, row_index), colors.HexColor('#f4f6f9')))
            results_table.setStyle(TableStyle(table_style))
            elements.append(results_table)
            elements.append(Spacer(1, 0.2 * inch))
    else:
        elements.append(Paragraph("No students have submitted this exam yet.", styles['Normal']))

    def _add_page_number(canvas, doc_):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#888888'))
        canvas.drawRightString(
            doc_.pagesize[0] - 0.5 * inch, 0.3 * inch, f"Page {doc_.page}"
        )
        canvas.restoreState()

    doc.build(elements, onFirstPage=_add_page_number, onLaterPages=_add_page_number)

    pdf_bytes = buffer.getvalue()
    buffer.close()

    safe_title = re.sub(r'[^A-Za-z0-9_-]+', '_', f"{exam.subject.code}_{exam.title}").strip('_')
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{safe_title}_results.pdf"'
    return response


@instructor_required
def reopen_attempt(request, attempt_id):
    """Undoes an accidental/premature submission: clears the submitted flag
    and score so the student can go back into the exam and continue from
    where they left off. Their previously saved answers are untouched."""
    attempt = get_object_or_404(
        ExamAttempt, id=attempt_id, exam__subject__instructor=request.user
    )
    if request.method == 'POST':
        extra_minutes = request.POST.get('extra_minutes', '').strip()
        if extra_minutes.isdigit() and int(extra_minutes) > 0:
            attempt.extra_time_seconds += int(extra_minutes) * 60

        attempt.is_submitted = False
        attempt.submitted_at = None
        attempt.score = 0
        attempt.total_points = 0
        attempt.save(update_fields=[
            'is_submitted', 'submitted_at', 'score', 'total_points', 'extra_time_seconds',
        ])
        messages.success(
            request,
            f"{attempt.student.get_full_name()}'s attempt has been reopened - "
            f"they can log back in and continue where they left off."
        )
    return redirect('exams:exam_results', exam_id=attempt.exam_id)


@instructor_required
def grant_extra_time(request, attempt_id):
    """Adds extra minutes to an in-progress attempt - e.g. to make up for a
    power/network interruption during the exam."""
    attempt = get_object_or_404(
        ExamAttempt, id=attempt_id, exam__subject__instructor=request.user
    )
    if request.method == 'POST':
        extra_minutes = request.POST.get('extra_minutes', '').strip()
        if extra_minutes.isdigit() and int(extra_minutes) > 0:
            attempt.extra_time_seconds += int(extra_minutes) * 60
            attempt.save(update_fields=['extra_time_seconds'])
            messages.success(
                request,
                f"Added {extra_minutes} extra minute(s) for {attempt.student.get_full_name()}."
            )
        else:
            messages.error(request, "Enter a valid whole number of minutes.")
    return redirect('exams:exam_results', exam_id=attempt.exam_id)


@instructor_required
def delete_in_progress_attempt(request, attempt_id):
    """Permanently removes an in-progress (not yet submitted) attempt - e.g.
    a student who started by mistake, or who won't be continuing the exam.
    This is deliberately separate from "Reopen": reopening restores a
    student's submitted work so they can keep going, while this permanently
    discards an attempt and its saved answers so far, freeing the student to
    start a completely fresh attempt if they access the exam again."""
    attempt = get_object_or_404(
        ExamAttempt, id=attempt_id, exam__subject__instructor=request.user
    )
    if attempt.is_submitted:
        messages.error(
            request,
            "This attempt has already been submitted - use \"Reopen\" instead "
            "if you want the student to continue it, rather than deleting it."
        )
        return redirect('exams:exam_results', exam_id=attempt.exam_id)

    if request.method == 'POST':
        student_name = attempt.student.get_full_name()
        exam_id = attempt.exam_id
        attempt.delete()
        messages.success(
            request,
            f"Deleted {student_name}'s in-progress attempt. They can start a fresh attempt if they access this exam again."
        )
        return redirect('exams:exam_results', exam_id=exam_id)
    return redirect('exams:exam_results', exam_id=attempt.exam_id)
