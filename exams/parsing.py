"""
Parser for bulk-importing exam questions from a plain text (.txt) file
or pasted text, e.g. written in Notepad.

Three input formats are supported. The first two can be mixed in one file;
Programming Multiple Choice uses its own numbered, three-part format so code
can contain blank lines without being split into separate questions.
For the first two formats, each question is a "block" of text and blocks are
separated by one or more blank lines.

--------------------------------------------------------------------
FORMAT 1 - Structured (supports all question types)
--------------------------------------------------------------------
    TYPE: MCQ
    Q: What is the capital of France?
    POINTS: 2
    A) Paris *
    B) London
    C) Berlin
    D) Madrid

    TYPE: TF
    Q: The Philippines has 7,641 islands.
    POINTS: 1
    ANSWER: True

    TYPE: IDENT
    Q: What is H2O commonly known as?
    POINTS: 1
    KEY: Water
    KEY: H2O

    TYPE: ENUM
    Q: Name 3 branches of government.
    POINTS: 3
    EXPECTED: 3
    KEY: Executive
    KEY: Legislative
    KEY: Judicial

    TYPE: CASE
    Q: Explain the causes of World War I.
    POINTS: 5
    KEY: nationalism
    KEY: alliances
    KEY: imperialism

    TYPE: MATCH
    Q: Match each term in Column A with the correct definition in Column B.
    POINTS: 3
    PAIR: SaaS = Software as a Service
    PAIR: IaaS = Infrastructure as a Service
    PAIR: PaaS = Platform as a Service
    DISTRACTOR: Network as a Service

--------------------------------------------------------------------
FORMAT 2 - Simple Multiple Choice (question + lettered choices + key)
--------------------------------------------------------------------
    What is Google Sheets mainly used for?
    A. Video editing
    B. Organizing and analyzing data
    C. Playing games
    D. Designing websites
    Answer Key: B

Rules for Format 2:
- The first line is the question text.
- Choice lines start with a letter followed by "." or ")", e.g. "A.", "B)".
- The last line gives the correct letter: "Answer Key: B", "Answer: B",
  or "Ans: B" all work.
- Every Format 2 question defaults to 1 point.
--------------------------------------------------------------------

Windows/Notepad line endings (\\r\\n) are handled automatically.

--------------------------------------------------------------------
FORMAT 3 - Programming Multiple Choice
--------------------------------------------------------------------
    1. Analyze the output of the code.

    num1 = 5
    num2 = 10
    print("Hello World!", num1 + num2)

    A. Hello World
    B. Hello World! 5
    C. 5
    D. Hello World! 15 *

The first block is the question, the final run of lettered lines is the
choice block, and everything between them is preserved as code. Exactly one
choice must end in an asterisk.
"""
import re

VALID_TYPES = {'MCQ', 'TF', 'ENUM', 'IDENT', 'CASE', 'MATCH'}
ANSWER_KEY_RE = re.compile(r'^(answer\s*key|answer|ans)\s*:\s*([A-Za-z])\s*$', re.IGNORECASE)
CHOICE_RE = re.compile(r'^([A-Za-z])[.)]\s*(.+)$')
TF_ANSWER_RE = re.compile(r'^answer\s*:\s*(true|false)\s*$', re.IGNORECASE)
PAIR_RE = re.compile(r'^PAIR\s*:\s*(.+?)\s*=\s*(.+)$', re.IGNORECASE)
DISTRACTOR_RE = re.compile(r'^DISTRACTOR\s*:\s*(.+)$', re.IGNORECASE)
PROGRAMMING_START_RE = re.compile(r'^(\d+)[.)](?:\s+(.*))?$')
PROGRAMMING_CHOICE_RE = re.compile(r'^([A-Za-z])[.)]\s+(.+)$')
TRAILING_CORRECT_RE = re.compile(r'\s*\*\s*$')


class BulkImportError(Exception):
    def __init__(self, message, block_number=None):
        self.message = message
        self.block_number = block_number
        super().__init__(message)


def _split_into_blocks(raw_text):
    """Split on one-or-more blank lines into a list of non-empty line lists."""
    normalized = raw_text.replace('\r\n', '\n').replace('\r', '\n')
    blocks = []
    current = []
    for line in normalized.split('\n'):
        if line.strip() == '':
            if current:
                blocks.append(current)
                current = []
        else:
            current.append(line)
    if current:
        blocks.append(current)
    return blocks


def _parse_structured_block(lines, idx):
    data = {
        'question_type': None,
        'points': 1,
        'expected_answer_count': None,
        'choices': [],
        'keys': [],
        'tf_answer': None,
        'pairs': [],
        'distractors': [],
    }
    question_text_parts = []

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            continue
        upper = stripped.upper()

        if upper.startswith('TYPE:'):
            value = stripped.split(':', 1)[1].strip().upper()
            if value not in VALID_TYPES:
                raise BulkImportError(
                    f"Question {idx}: unknown TYPE '{value}'. Must be one of MCQ, TF, ENUM, IDENT, CASE, MATCH.", idx
                )
            data['question_type'] = value

        elif upper.startswith('Q:'):
            question_text_parts.append(stripped.split(':', 1)[1].strip())

        elif upper.startswith('POINTS:'):
            value = stripped.split(':', 1)[1].strip()
            if not value.isdigit() or int(value) < 1:
                raise BulkImportError(f"Question {idx}: POINTS must be a whole number of at least 1.", idx)
            data['points'] = int(value)

        elif upper.startswith('EXPECTED:'):
            value = stripped.split(':', 1)[1].strip()
            if not value.isdigit() or int(value) < 1:
                raise BulkImportError(f"Question {idx}: EXPECTED must be a whole number of at least 1.", idx)
            data['expected_answer_count'] = int(value)

        elif TF_ANSWER_RE.match(stripped):
            data['tf_answer'] = TF_ANSWER_RE.match(stripped).group(1).lower()

        elif PAIR_RE.match(stripped):
            m = PAIR_RE.match(stripped)
            left, right = m.group(1).strip(), m.group(2).strip()
            if left and right:
                data['pairs'].append((left, right))

        elif DISTRACTOR_RE.match(stripped):
            value = DISTRACTOR_RE.match(stripped).group(1).strip()
            if value:
                data['distractors'].append(value)

        elif upper.startswith('KEY:'):
            value = stripped.split(':', 1)[1].strip()
            if value:
                data['keys'].append(value)

        elif re.match(r'^[A-Za-z]\)', stripped):
            text = stripped[2:].strip()
            is_correct = False
            if text.endswith('*'):
                is_correct = True
                text = text[:-1].strip()
            data['choices'].append((text, is_correct))

        else:
            question_text_parts.append(stripped)

    data['question_text'] = ' '.join(question_text_parts).strip()

    if not data['question_type']:
        raise BulkImportError(f"Question {idx}: missing a TYPE: line.", idx)
    if not data['question_text']:
        raise BulkImportError(f"Question {idx}: missing question text (a 'Q: ...' line).", idx)

    if data['question_type'] == 'MCQ':
        if len(data['choices']) < 2:
            raise BulkImportError(
                f"Question {idx}: Multiple Choice needs at least 2 choices (lines like 'A) ...').", idx
            )
        if not any(is_correct for _, is_correct in data['choices']):
            raise BulkImportError(
                f"Question {idx}: no choice is marked correct. End the correct choice's line with '*'.", idx
            )

    elif data['question_type'] == 'TF':
        if data['tf_answer'] in ('true', 'false'):
            data['choices'] = [
                ('True', data['tf_answer'] == 'true'),
                ('False', data['tf_answer'] == 'false'),
            ]
        elif len(data['choices']) >= 2 and any(is_correct for _, is_correct in data['choices']):
            pass  # provided the long way, via A)/B) lines with '*' - treat like MCQ
        else:
            raise BulkImportError(
                f"Question {idx}: True/False needs an 'ANSWER: True' or 'ANSWER: False' line.", idx
            )

    elif data['question_type'] == 'MATCH':
        if len(data['pairs']) < 2:
            raise BulkImportError(
                f"Question {idx}: Matching Type needs at least 2 'PAIR: left = right' lines.", idx
            )

    else:
        if not data['keys']:
            raise BulkImportError(
                f"Question {idx}: needs at least one 'KEY: ...' line as the answer key.", idx
            )
        if data['expected_answer_count'] is None:
            data['expected_answer_count'] = len(data['keys']) if data['question_type'] == 'ENUM' else 1

    if data['expected_answer_count'] is None:
        data['expected_answer_count'] = 1

    return data


def _parse_simple_mcq_block(lines, idx):
    question_lines = []
    choices = []  # list of (letter, text)
    answer_letter = None

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            continue

        m_answer = ANSWER_KEY_RE.match(stripped)
        if m_answer:
            answer_letter = m_answer.group(2).upper()
            continue

        m_choice = CHOICE_RE.match(stripped)
        if m_choice:
            letter = m_choice.group(1).upper()
            text = m_choice.group(2).strip()
            choices.append((letter, text))
            continue

        # Anything before the first choice line is part of the question text.
        if not choices:
            question_lines.append(stripped)
        # Stray lines appearing after choices started (and not matching a
        # choice or an answer key line) are ignored rather than crashing
        # the whole import.

    question_text = ' '.join(question_lines).strip()

    if not question_text:
        raise BulkImportError(f"Question {idx}: could not detect the question text.", idx)
    if len(choices) < 2:
        raise BulkImportError(
            f"Question {idx}: needs at least 2 choices (lines like 'A. ...', 'B. ...').", idx
        )
    if not answer_letter:
        raise BulkImportError(
            f"Question {idx}: missing an answer line (e.g. 'Answer Key: B').", idx
        )
    if not any(letter == answer_letter for letter, _ in choices):
        raise BulkImportError(
            f"Question {idx}: Answer Key '{answer_letter}' doesn't match any of the listed choices "
            f"({', '.join(letter for letter, _ in choices)}).", idx
        )

    return {
        'question_type': 'MCQ',
        'question_text': question_text,
        'points': 1,
        'expected_answer_count': 1,
        'choices': [(text, letter == answer_letter) for letter, text in choices],
        'keys': [],
    }


def _normalize_lines(raw_text):
    normalized = raw_text.replace('\r\n', '\n').replace('\r', '\n')
    if normalized.startswith('\ufeff'):
        normalized = normalized[1:]
    lines = normalized.split('\n')
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def _choice_run_before(lines, boundary):
    """Return True when the content before boundary ends in 2+ choices."""
    index = boundary - 1
    while index >= 0 and not lines[index].strip():
        index -= 1
    count = 0
    while index >= 0 and PROGRAMMING_CHOICE_RE.match(lines[index]):
        count += 1
        index -= 1
    return count >= 2


def _split_programming_questions(lines):
    """Split only at numbered starts that follow a completed choice block.

    A numbered-looking line inside code is therefore kept as code, even when
    it follows a blank line.
    """
    boundaries = [0]
    for index in range(1, len(lines)):
        if (
            PROGRAMMING_START_RE.match(lines[index])
            and not lines[index - 1].strip()
            and _choice_run_before(lines, index)
        ):
            boundaries.append(index)
    boundaries.append(len(lines))
    return [lines[start:end] for start, end in zip(boundaries, boundaries[1:])]


def _looks_like_programming_mcq(raw_text):
    lines = _normalize_lines(raw_text)
    if not lines or not PROGRAMMING_START_RE.match(lines[0]):
        return False
    # An answer-key line identifies the established quick-MCQ format. A
    # numbered first block followed by a blank line identifies the new format,
    # including malformed questions that still need a question-numbered error.
    if ANSWER_KEY_RE.match(lines[-1].strip()):
        return False
    return any(not line.strip() for line in lines[1:])


def _parse_programming_question(lines):
    while lines and not lines[-1].strip():
        lines.pop()

    start_match = PROGRAMMING_START_RE.match(lines[0]) if lines else None
    question_number = start_match.group(1) if start_match else '?'
    error_prefix = f"Question {question_number}:"

    first_blank = next((i for i, line in enumerate(lines) if not line.strip()), None)
    if not start_match or first_blank is None:
        raise BulkImportError(
            f"{error_prefix} missing question text or its separating blank line.", question_number
        )

    first_question_line = start_match.group(2) or ''
    question_text = '\n'.join([first_question_line, *lines[1:first_blank]]).strip()
    if not question_text:
        raise BulkImportError(f"{error_prefix} missing question text.", question_number)

    choice_start = len(lines)
    while choice_start > first_blank + 1 and PROGRAMMING_CHOICE_RE.match(lines[choice_start - 1]):
        choice_start -= 1
    choice_lines = lines[choice_start:]
    if len(choice_lines) < 2:
        raise BulkImportError(
            f"{error_prefix} missing choices (add at least two trailing lines like 'A. Choice').",
            question_number,
        )
    if choice_start == 0 or lines[choice_start - 1].strip():
        raise BulkImportError(
            f"{error_prefix} code and choices must be separated by a blank line.", question_number
        )

    code_lines = lines[first_blank + 1:choice_start]
    while code_lines and not code_lines[0].strip():
        code_lines.pop(0)
    while code_lines and not code_lines[-1].strip():
        code_lines.pop()
    if not code_lines or not any(line.strip() for line in code_lines):
        raise BulkImportError(f"{error_prefix} missing code.", question_number)
    code_snippet = '\n'.join(code_lines)

    choices = []
    marked_count = 0
    for line in choice_lines:
        match = PROGRAMMING_CHOICE_RE.match(line)
        choice_text = match.group(2)
        is_correct = bool(TRAILING_CORRECT_RE.search(choice_text))
        if is_correct:
            marked_count += 1
            choice_text = TRAILING_CORRECT_RE.sub('', choice_text)
        choice_text = choice_text.strip()
        if not choice_text:
            raise BulkImportError(f"{error_prefix} contains an empty choice.", question_number)
        choices.append((choice_text, is_correct))

    if marked_count != 1:
        raise BulkImportError(
            f"{error_prefix} exactly one choice must end with '*'; found {marked_count}.",
            question_number,
        )

    return {
        'question_type': 'PMCQ',
        'question_text': question_text,
        'code_snippet': code_snippet,
        'code_language': '',
        'points': 1,
        'expected_answer_count': 1,
        'choices': choices,
        'keys': [],
        'pairs': [],
        'distractors': [],
    }


def _parse_programming_questions(raw_text, max_new_items):
    question_blocks = _split_programming_questions(_normalize_lines(raw_text))
    if len(question_blocks) > max_new_items:
        raise BulkImportError(
            f"This text contains {len(question_blocks)} question(s), but this exam only has room "
            f"for {max_new_items} more before reaching the 100-item limit."
        )
    return [_parse_programming_question(block) for block in question_blocks]


def parse_bulk_questions(raw_text, max_new_items):
    if _looks_like_programming_mcq(raw_text):
        return _parse_programming_questions(raw_text, max_new_items)

    blocks = _split_into_blocks(raw_text)

    if not blocks:
        raise BulkImportError(
            "No questions were found in the text provided. Please check the format and try again."
        )

    if len(blocks) > max_new_items:
        raise BulkImportError(
            f"This text contains {len(blocks)} question(s), but this exam only has room "
            f"for {max_new_items} more before reaching the 100-item limit."
        )

    parsed_questions = []
    for idx, block_lines in enumerate(blocks, start=1):
        first_meaningful_line = next((l.strip() for l in block_lines if l.strip()), '')
        if first_meaningful_line.upper().startswith('TYPE:'):
            parsed_questions.append(_parse_structured_block(block_lines, idx))
        else:
            parsed_questions.append(_parse_simple_mcq_block(block_lines, idx))

    return parsed_questions
