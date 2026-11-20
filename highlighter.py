import os
import re
from pathlib import Path

import pymupdf

# -------------------- SETTINGS --------------------

QUESTION_MIN = 1
QUESTION_MAX = 1000
HIGHLIGHT_GREEN = (6 / 255, 85 / 255, 53 / 255)
HIGHLIGHT_YELLOW = (1.0, 0.85, 0.0)
HIGHLIGHT_OPACITY = 0.30


# -------------------- ANSWER KEY --------------------

def extract_answer_key(doc):
    """Extract question-number/option-number pairs from the final PDF page."""
    if len(doc) == 0:
        raise ValueError("The PDF is empty.")

    text = doc[-1].get_text("text")
    key_pos = text.upper().rfind("KEY")
    if key_pos < 0:
        raise ValueError("Could not find 'KEY' on the last PDF page.")

    key_text = text[key_pos:]
    matches = re.findall(
        r"(?<!\d)(\d{1,3})\s*\.\s*([1-5])(?!\d)",
        key_text
    )

    answers = {}
    for q_text, option_text in matches:
        q, option = int(q_text), int(option_text)
        if QUESTION_MIN <= q <= QUESTION_MAX:
            answers[q] = option

    if not answers:
        raise ValueError("The KEY was found, but no answers could be extracted.")

    print(f"\nAnswer key detected: {len(answers)} question(s).")
    return answers


# -------------------- PDF TEXT GEOMETRY --------------------

def get_lines(page):
    """Extract text lines with individual character coordinates."""
    raw = page.get_text("rawdict")
    result = []

    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue

        for line in block.get("lines", []):
            spans = line.get("spans", [])
            chars = [
                char
                for span in spans
                for char in span.get("chars", [])
            ]
            if not chars:
                continue

            text = "".join(char.get("c", "") for char in chars)
            if text.strip():
                result.append({"text": text, "chars": chars})

    return result


def make_rect(chars, start=0, end=None):
    """Create a rectangle around a selected range of PDF characters."""
    if end is None:
        end = len(chars)

    selected = chars[max(0, start):min(len(chars), end)]
    boxes = [c["bbox"] for c in selected if c.get("bbox")]
    if not boxes:
        return None

    return pymupdf.Rect(
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def option_markers(text):
    """
    Find option labels 1) through 5), without requiring spaces.

    Handles joined labels such as '...II4) Only I' and labels whose
    answer text is on the next PDF line, such as a standalone '4) '.
    """
    return list(re.finditer(r"(?<!\d)([1-5])\)", text))


def add_highlight(page, rect, color):
    if rect is None or rect.is_empty:
        return
    annot = page.add_highlight_annot(rect)
    annot.set_colors(stroke=color)
    annot.set_opacity(HIGHLIGHT_OPACITY)
    annot.update()


# -------------------- PDF PROCESSING --------------------

def process_pdf(input_path):
    input_path = Path(input_path)

    if not input_path.exists():
        raise FileNotFoundError(f"File not found: {input_path}")
    if input_path.suffix.lower() != ".pdf":
        raise ValueError("Please upload a PDF file.")

    print(f"\nOpening: {input_path.name}")
    doc = pymupdf.open(str(input_path))

    try:
        answers = extract_answer_key(doc)

        questions_seen = set()
        correct_options_found = {}
        # Store (page_number, rectangle) so failed questions can be marked yellow.
        option_rectangles = {}
        total_green = 0

        for page_index, page in enumerate(doc):
            lines = get_lines(page)
            current_question = None
            continuation_question = None
            structured_question = False

            for line in lines:
                text = line["text"]

                # Do not process the answer-key section as question content.
                if re.match(r"^\s*KEY\b", text, re.IGNORECASE):
                    current_question = None
                    continuation_question = None
                    structured_question = False
                    continue

                # Detect question numbers, including a number on its own line.
                q_match = re.match(r"^\s*(\d{1,3})\.(?:\s|$)", text)
                if q_match:
                    q = int(q_match.group(1))
                    current_question = q if q in answers else None
                    continuation_question = None
                    structured_question = False
                    if current_question is not None:
                        questions_seen.add(current_question)
                    continue

                # Detect direction groups such as Direction (1-5).
                direction_match = re.search(
                    r"\bDirections?\s*:?\s*\(\s*(\d{1,3})"
                    r"(?:\s*[-–—]\s*(\d{1,3}))?\s*\)",
                    text,
                    re.IGNORECASE,
                )
                if direction_match:
                    continuation_question = None
                    first_q = int(direction_match.group(1))
                    last_q = direction_match.group(2)

                    if last_q is not None:
                        current_question = None
                        structured_question = False
                    else:
                        current_question = first_q if first_q in answers else None
                        structured_question = current_question is not None
                        if current_question is not None:
                            questions_seen.add(current_question)
                    continue

                markers = option_markers(text)

                # In a single-question direction group, wait for its options.
                if structured_question:
                    if not markers:
                        continue
                    structured_question = False

                if current_question is None:
                    continue

                if markers:
                    continuation_question = None
                    option_rectangles.setdefault(current_question, [])

                    # Record all visible option ranges for possible yellow fallback.
                    for i, marker in enumerate(markers):
                        start = marker.start(1)
                        end = markers[i + 1].start() if i + 1 < len(markers) else len(text)
                        while end > start and text[end - 1].isspace():
                            end -= 1

                        rect = make_rect(line["chars"], start, end)
                        if rect is not None:
                            option_rectangles[current_question].append(
                                (page_index, rect)
                            )

                    # Locate and highlight the answer-key option.
                    wanted = answers[current_question]
                    matching = [
                        (i, marker)
                        for i, marker in enumerate(markers)
                        if int(marker.group(1)) == wanted
                    ]

                    if matching:
                        i, marker = matching[0]
                        start = marker.start(1)
                        end = markers[i + 1].start() if i + 1 < len(markers) else len(text)
                        while end > start and text[end - 1].isspace():
                            end -= 1

                        rect = make_rect(line["chars"], start, end)
                        if rect is not None:
                            add_highlight(page, rect, HIGHLIGHT_GREEN)
                            total_green += 1
                            correct_options_found[current_question] = (
                                correct_options_found.get(current_question, 0) + 1
                            )

                        # Continue onto the next line if this was the final
                        # option label on the current line.
                        if i == len(markers) - 1:
                            continuation_question = current_question

                elif continuation_question == current_question:
                    # Handle option values split onto their own PDF text lines.
                    if text.strip() and not re.match(r"^\s*\d{1,3}\.", text):
                        rect = make_rect(line["chars"])
                        if rect is not None:
                            add_highlight(page, rect, HIGHLIGHT_GREEN)
                            total_green += 1
                            correct_options_found[current_question] = (
                                correct_options_found.get(current_question, 0) + 1
                            )
                            option_rectangles.setdefault(current_question, []).append(
                                (page_index, rect)
                            )
                    else:
                        continuation_question = None

            print(
                f"  Page {page_index + 1:2}/{len(doc)} processed",
                end="\r"
            )

        print()

        # -------------------- NON-FATAL CROSS-CHECK --------------------

        missing_questions = sorted(set(answers) - questions_seen)
        failed_matches = sorted(
            q for q in answers
            if correct_options_found.get(q, 0) < 1
        )

        # Cross-check failure is a warning, NOT an exception.
        # Mark every located option for an unmatched question in yellow.
        yellow_count = 0
        for q in failed_matches:
            for page_index, rect in option_rectangles.get(q, []):
                add_highlight(doc[page_index], rect, HIGHLIGHT_YELLOW)
                yellow_count += 1

        if missing_questions or failed_matches:
            print("\nWARNING: ANSWER-KEY CROSS-CHECK NEEDS REVIEW.")
            if missing_questions:
                print("Questions not detected in question pages:",
                      ", ".join(map(str, missing_questions)))
            if failed_matches:
                print("Correct option could not be matched:",
                      ", ".join(map(str, failed_matches)))
                print("Their detected option text has been marked yellow.")
            print("The PDF will still be saved and downloaded.")
        else:
            print(
                f"Answer-key cross-check passed: all {len(answers)} "
                "questions matched."
            )

        # -------------------- SAVE OUTPUT --------------------

        output_path = input_path.with_name(
            input_path.stem + " with answers" + input_path.suffix
        )

        if output_path.exists():
            output_path.unlink()

        doc.save(str(output_path), garbage=4, deflate=True)

        print("\nSuccessfully created:")
        print(output_path)
        print(f"Answer-key questions: {len(answers)}")
        print(f"Questions detected: {len(questions_seen)}")
        print(f"Green highlight segments: {total_green}")
        print(f"Yellow fallback segments: {yellow_count}")

        return output_path

    finally:
        doc.close()


# Web backend calls process_pdf(input_path) directly.
