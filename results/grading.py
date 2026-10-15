"""
Auto-grading engine for the LAN Examination System.

- Multiple Choice / True-or-False: exact match against the choice marked correct.
- Identification: case-insensitive / whitespace-insensitive match against
  any of the accepted answers in the instructor's answer key.
- Enumeration: the student's answer (one item per line, or comma
  separated) is compared against the answer key list. Partial credit is
  given proportional to how many expected items were correctly supplied.
- Case Analysis: keyword-matching against the answer key's key concepts.
  Because this is essay/typed input, it is flagged for optional manual
  review by the instructor even though a score is generated immediately.
- Matching Type: the student's submitted {pair_id: chosen_text} mapping
  (stored as JSON) is compared against each pair's correct right_text.
  Partial credit proportional to how many pairs were matched correctly.
"""
import json

from exams.models import Question


def _normalize(text):
    return ' '.join(text.strip().lower().split())


def grade_mcq(question, selected_choice):
    if selected_choice is None:
        return 0
    return question.points if selected_choice.is_correct else 0


def grade_identification(question, text_answer):
    if not hasattr(question, 'answer_key'):
        return 0
    accepted = [_normalize(a) for a in question.answer_key.answers_list()]
    return question.points if _normalize(text_answer or '') in accepted else 0


def _split_student_items(text_answer):
    raw = (text_answer or '').replace(',', '\n')
    return [item.strip() for item in raw.splitlines() if item.strip()]


def grade_enumeration(question, text_answer):
    if not hasattr(question, 'answer_key'):
        return 0
    expected = [_normalize(a) for a in question.answer_key.answers_list()]
    if not expected:
        return 0
    given = [_normalize(a) for a in _split_student_items(text_answer)]
    matches = 0
    remaining = list(expected)
    for item in given:
        if item in remaining:
            remaining.remove(item)
            matches += 1
    ratio = matches / len(expected)
    return round(ratio * question.points)


def grade_case_analysis(question, text_answer):
    if not hasattr(question, 'answer_key'):
        return 0
    keywords = [_normalize(a) for a in question.answer_key.answers_list()]
    if not keywords:
        return 0
    normalized_answer = _normalize(text_answer or '')
    matched = sum(1 for kw in keywords if kw and kw in normalized_answer)
    ratio = matched / len(keywords)
    return round(ratio * question.points)


def parse_matching_answer(text_answer):
    """The student's Matching answer is stored as JSON: {pair_id: chosen_text}."""
    if not text_answer:
        return {}
    try:
        parsed = json.loads(text_answer)
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return {}


def grade_matching(question, text_answer):
    pairs = list(question.matching_pairs.all())
    if not pairs:
        return 0
    submitted = parse_matching_answer(text_answer)
    matches = 0
    for pair in pairs:
        chosen = submitted.get(str(pair.id), '')
        if _normalize(chosen) == _normalize(pair.right_text):
            matches += 1
    ratio = matches / len(pairs)
    return round(ratio * question.points)


def grade_answer(question, selected_choice=None, text_answer=''):
    """Returns (points_earned, needs_manual_review)."""
    if question.question_type in (Question.MCQ, Question.TF):
        return grade_mcq(question, selected_choice), False
    if question.question_type == Question.IDENT:
        return grade_identification(question, text_answer), False
    if question.question_type == Question.ENUM:
        return grade_enumeration(question, text_answer), False
    if question.question_type == Question.MATCH:
        return grade_matching(question, text_answer), False
    if question.question_type == Question.CASE:
        # Auto-scored via keyword matching, but flagged so the instructor
        # can double-check essay-style answers if they choose to.
        return grade_case_analysis(question, text_answer), True
    return 0, False
