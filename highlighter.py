import re
from pathlib import Path

import pymupdf

# -------------------- APPLICATION LIMITS --------------------

QUESTION_MIN = 1
QUESTION_MAX = 1000

MAX_FILE_SIZE = 20 * 1024 * 1024       # 20 MB
MIN_PAGES = 1
MAX_PAGES = 20

HIGHLIGHT_GREEN = (6 / 255, 85 / 255, 53 / 255)
HIGHLIGHT_YELLOW = (1.0, 0.85, 0.0)
HIGHLIGHT_OPACITY = 0.30


# -------------------- PROGRESS / ERRORS --------------------

def report(message, progress_callback=None):
    """Send a progress message to the web app and also print it to logs."""
    print(message, flush=True)
    if progress_callback:
        try:
            progress_callback(message)
        except Exception:
            # A progress-display problem must not stop PDF processing.
            pass


class PDFValidationError(ValueError):
    """A safe, user-facing upload validation error."""


# -------------------- UPLOAD VALIDATION --------------------

def validate_upload(input_path):
    """
    Validate the uploaded file before answer-key extraction or highlighting.

    Checks filename, extension, size, PDF signature, readability, encryption,
    page count, extractable text, question-paper structure and answer key.
    Returns an opened PyMuPDF document. Caller must close it.
    """
    input_path = Path(input_path)

    if not input_path.exists() or not input_path.is_file():
        raise PDFValidationError("Upload failed: the selected file was not found.")

    # 1. Filename pattern.
    #Handled by app.py

    # 2. Extension.
    if input_path.suffix.lower() != ".pdf":
        raise PDFValidationError("Invalid file type. Please upload a PDF file.")

    # 3. File size.
    try:
        file_size = input_path.stat().st_size
    except OSError:
        raise PDFValidationError("The uploaded file could not be read.")

    if file_size <= 0:
        raise PDFValidationError("The uploaded PDF is empty.")

    if file_size > MAX_FILE_SIZE:
        raise PDFValidationError("File too large. Maximum allowed size is 20 MB.")

    # 4. PDF signature (do not trust the extension or browser MIME type).
    try:
        with input_path.open("rb") as file_handle:
            signature = file_handle.read(5)
    except OSError:
        raise PDFValidationError("The uploaded file could not be read.")

    if signature != b"%PDF-":
        raise PDFValidationError(
            "Invalid PDF: the file does not contain a valid PDF signature."
        )

    # 5. Open and parse the actual PDF.
    try:
        doc = pymupdf.open(str(input_path))
    except Exception as exc:
        raise PDFValidationError(
            "Corrupted or unreadable PDF. Please open the file on your device "
            "and upload a working copy."
        ) from exc

    try:
        if not doc.is_pdf:
            raise PDFValidationError("The uploaded file is not a valid PDF.")

        # 6. Encrypted/password-protected files.
        if doc.needs_pass:
            raise PDFValidationError(
                "Password-protected PDF. Please remove the password and upload "
                "an unlocked PDF."
            )

        if getattr(doc, "is_encrypted", False):
            # Some PDFs report encrypted even when an empty password works.
            try:
                authenticated = doc.authenticate("")
            except Exception:
                authenticated = 0
            if not authenticated:
                raise PDFValidationError(
                    "Password-protected PDF. Please upload an unlocked PDF."
                )

        # 7. Page count.
        page_count = len(doc)
        if page_count < MIN_PAGES:
            raise PDFValidationError("The PDF contains no pages.")
        if page_count > MAX_PAGES:
            raise PDFValidationError(
                "Page limit exceeded. A maximum of 20 pages is allowed."
            )

        # 8. Extractable text. Scanned/image-only PDFs are not supported.
        page_texts = []
        total_text_chars = 0
        for page in doc:
            try:
                page_text = page.get_text("text") or ""
            except Exception as exc:
                raise PDFValidationError(
                    "The PDF contains unreadable page content."
                ) from exc
            page_texts.append(page_text)
            total_text_chars += len(re.sub(r"\s+", "", page_text))

        if total_text_chars < 30:
            raise PDFValidationError(
                "No usable selectable text was found. Scanned/image-only PDFs "
                "are not supported; please upload a text-based PDF."
            )

        # 9. Check for recognisable question-paper content on pages before
        # the final answer-key page. Keep this broad enough for different layouts.
        question_pages_text = "\n".join(page_texts[:-1] if page_count > 1 else page_texts)
        question_number_pattern = re.compile(
            r"(?im)^\s*(?:Q(?:uestion)?\s*)?\d{1,3}\s*[.)]\s+"
        )
        option_pattern = re.compile(r"(?<!\d)[1-5]\s*[)]")

        question_number_hits = len(question_number_pattern.findall(question_pages_text))
        option_hits = len(option_pattern.findall(question_pages_text))

        if question_number_hits == 0:
            raise PDFValidationError(
                "Unsupported document: question numbers were not recognised. "
                "Please upload a Sreedhar's Institute Model Test question paper."
            )

        if option_hits < 2:
            raise PDFValidationError(
                "Unsupported document: multiple-choice options were not "
                "recognised. Please upload the original Model Test question paper."
            )

        # 10. Answer key must be present and extractable on the final page.
        last_page_text = page_texts[-1]
        if not re.search(r"\bKEY\b", last_page_text, re.IGNORECASE):
            raise PDFValidationError(
                "Answer key not detected on the last page. Please check that "
                "you uploaded the complete Model Test PDF."
            )

        key_pos = last_page_text.upper().rfind("KEY")
        key_text = last_page_text[key_pos:]
        answer_pairs = re.findall(
            r"(?<!\d)(\d{1,3})\s*\.\s*([1-5])(?!\d)",
            key_text
        )
        valid_pairs = [
            (int(q), int(opt))
            for q, opt in answer_pairs
            if QUESTION_MIN <= int(q) <= QUESTION_MAX
        ]

        if not valid_pairs:
            raise PDFValidationError(
                "The answer key heading was found, but no readable answers "
                "could be extracted from the last page."
            )

        # At least one extracted key item must correspond to a question number
        # detected in the question pages. This helps reject unrelated PDFs
        # that happen to contain the word KEY and numbered lists.
        detected_numbers = {
            int(match)
            for match in re.findall(
                r"(?im)^\s*(?:Q(?:uestion)?\s*)?(\d{1,3})\s*[.)]\s+",
                question_pages_text
            )
        }
        if detected_numbers and not any(q in detected_numbers for q, _ in valid_pairs):
            raise PDFValidationError(
                "The answer key does not appear to match the question pages. "
                "Please upload the complete original Model Test PDF."
            )

        report(
            f"Upload validation passed: {input_path.name} "
            f"({page_count} page(s), {file_size / (1024 * 1024):.2f} MB)."
        )
        return doc

    except Exception:
        doc.close()
        raise


# -------------------- ANSWER KEY --------------------

def extract_answer_key(doc):
    """Extract question-number/option-number pairs from the final PDF page."""
    if len(doc) == 0:
        raise PDFValidationError("The PDF is empty.")

    text = doc[-1].get_text("text")
    key_pos = text.upper().rfind("KEY")
    if key_pos < 0:
        raise PDFValidationError("Could not find 'KEY' on the last PDF page.")

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
        raise PDFValidationError(
            "The answer key was found, but no answers could be extracted."
        )

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
            chars = [
                char
                for span in line.get("spans", [])
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
    boxes = [char["bbox"] for char in selected if char.get("bbox")]
    if not boxes:
        return None

    return pymupdf.Rect(
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def option_markers(text):
    """Find option labels 1) through 5), including labels without spaces."""
    return list(re.finditer(r"(?<!\d)([1-5])\)", text))


def add_highlight(page, rect, color):
    if rect is None or rect.is_empty:
        return

    annot = page.add_highlight_annot(rect)
    annot.set_colors(stroke=color)
    annot.set_opacity(HIGHLIGHT_OPACITY)
    annot.update()


# -------------------- PDF PROCESSING --------------------

def process_pdf(input_path, progress_callback=None):
    """
    Validate and process one Model Test PDF.

    The optional progress_callback(message) is used by the web app to stream
    processing logs to the browser. Existing callers may continue using
    process_pdf(input_path).
    """
    input_path = Path(input_path)
    report(f"Checking uploaded file: {input_path.name}", progress_callback)

    doc = validate_upload(input_path)

    try:
        report("Reading answer key...", progress_callback)
        answers = extract_answer_key(doc)
        report(f"Answer key detected: {len(answers)} question(s).", progress_callback)

        questions_seen = set()
        correct_options_found = {}
        option_rectangles = {}
        total_green = 0

        question_pages = max(1, len(doc) - 1)

        for page_index, page in enumerate(doc):
            report(
                f"Processing page {page_index + 1}/{len(doc)}...",
                progress_callback
            )
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

                # Detect direction groups such as Directions (1-5).
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

                if structured_question:
                    if not markers:
                        continue
                    structured_question = False

                if current_question is None:
                    continue

                if markers:
                    continuation_question = None
                    option_rectangles.setdefault(current_question, [])

                    # Store all visible options for yellow manual-review fallback.
                    for i, marker in enumerate(markers):
                        start = marker.start(1)
                        end = (
                            markers[i + 1].start()
                            if i + 1 < len(markers)
                            else len(text)
                        )
                        while end > start and text[end - 1].isspace():
                            end -= 1

                        rect = make_rect(line["chars"], start, end)
                        if rect is not None:
                            option_rectangles[current_question].append(
                                (page_index, rect)
                            )

                    wanted = answers[current_question]
                    matching = [
                        (i, marker)
                        for i, marker in enumerate(markers)
                        if int(marker.group(1)) == wanted
                    ]

                    if matching:
                        i, marker = matching[0]
                        start = marker.start(1)
                        end = (
                            markers[i + 1].start()
                            if i + 1 < len(markers)
                            else len(text)
                        )
                        while end > start and text[end - 1].isspace():
                            end -= 1

                        rect = make_rect(line["chars"], start, end)
                        if rect is not None:
                            add_highlight(page, rect, HIGHLIGHT_GREEN)
                            total_green += 1
                            correct_options_found[current_question] = (
                                correct_options_found.get(current_question, 0) + 1
                            )

                        if i == len(markers) - 1:
                            continuation_question = current_question

                elif continuation_question == current_question:
                    # Handle option text that wraps onto the next PDF text line.
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

        report("Checking answer matches...", progress_callback)

        # Cross-check failure is intentionally non-fatal.
        missing_questions = sorted(set(answers) - questions_seen)
        failed_matches = sorted(
            q for q in answers
            if correct_options_found.get(q, 0) < 1
        )

        yellow_count = 0
        for question in failed_matches:
            for page_index, rect in option_rectangles.get(question, []):
                add_highlight(doc[page_index], rect, HIGHLIGHT_YELLOW)
                yellow_count += 1

        if missing_questions or failed_matches:
            warning = (
                "WARNING: Some answers need manual review. "
                f"Questions not detected: {len(missing_questions)}; "
                f"questions without a matched correct option: {len(failed_matches)}. "
                "Available options for failed matches are marked yellow."
            )
            report(warning, progress_callback)
        else:
            report(
                f"Answer-key cross-check passed: all {len(answers)} questions matched.",
                progress_callback
            )

        # Save beside the uploaded file. The web app may use its own temp folder.
        output_path = input_path.with_name(
            input_path.stem + " with answers" + input_path.suffix
        )

        if output_path.exists():
            output_path.unlink()

        doc.save(str(output_path), garbage=4, deflate=True)

        report(
            f"Completed. Green highlights: {total_green}; "
            f"yellow manual-review segments: {yellow_count}.",
            progress_callback
        )
        return output_path

    finally:
        doc.close()
