
import os
import re
import json
import base64
import tempfile
import threading
import queue
from pathlib import Path

import pymupdf
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
from highlighter import process_pdf

app = Flask(__name__)

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
MAX_PAGES = 20

app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE

CORS(app, resources={r"/*": {"origins": "*"}})

# Accepted examples:
# Model Test 1.pdf
# Model Test 54.pdf
# Model Test 100.pdf
# Model Test 250.pdf
FILENAME_PATTERN = re.compile(
    r"^Model\s+Test\s+\d+\.pdf$",
    re.IGNORECASE
)


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "Sreedhars_MT_PDF_Solver"
    })


@app.post("/process")
def process():

    uploaded = request.files.get("file")

    if uploaded is None or not uploaded.filename:
        return jsonify({
            "error": "Please choose one PDF file."
        }), 400

    # Get the original filename supplied by the browser.
    original_name = uploaded.filename.replace("\\", "/").split("/")[-1]

    # Validate the ORIGINAL filename before saving it as input.pdf.
    if not FILENAME_PATTERN.fullmatch(original_name):
        return jsonify({
            "error": (
                "Invalid filename. Please use the format "
                "'Model Test 100.pdf' (the number may vary)."
            )
        }), 400

    download_name = (
        Path(original_name).stem + " with answers.pdf"
    )

    events = queue.Queue()

    def worker():

        try:
            with tempfile.TemporaryDirectory(
                prefix="sreedhars_pdf_"
            ) as temp_dir:

                # Internal filename is deliberately different.
                input_path = Path(temp_dir) / "input.pdf"

                uploaded.save(input_path)

                events.put({
                    "type": "log",
                    "message": f"Uploaded file: {original_name}"
                })

                events.put({
                    "type": "log",
                    "message": "Checking the PDF..."
                })

                # Check actual file size.
                file_size = input_path.stat().st_size

                if file_size > MAX_FILE_SIZE:
                    raise ValueError(
                        "File is too large. Maximum allowed size is 20 MB."
                    )

                if file_size == 0:
                    raise ValueError("The uploaded PDF is empty.")

                # Check PDF signature.
                with input_path.open("rb") as f:
                    if f.read(5) != b"%PDF-":
                        raise ValueError(
                            "The uploaded file is not a valid PDF."
                        )

                # Open and validate PDF.
                try:
                    with pymupdf.open(str(input_path)) as check_doc:

                        page_count = len(check_doc)

                        if page_count < 1:
                            raise ValueError("The PDF is empty.")

                        if page_count > MAX_PAGES:
                            raise ValueError(
                                f"The PDF has {page_count} pages. "
                                f"Maximum allowed is {MAX_PAGES}."
                            )

                        if check_doc.is_encrypted:
                            raise ValueError(
                                "Password-protected PDFs are not supported."
                            )

                except ValueError:
                    raise
                except Exception as exc:
                    raise ValueError(
                        "The PDF is damaged or cannot be opened."
                    ) from exc

                events.put({
                    "type": "log",
                    "message": (
                        f"PDF validated: {page_count} page(s)."
                    )
                })

                events.put({
                    "type": "log",
                    "message": "Starting answer-key detection..."
                })

                # Process the PDF. Progress messages are streamed
                # to the website through the callback.
                output_path = process_pdf(
                    input_path,
                    progress_callback=lambda message: events.put({
                        "type": "log",
                        "message": str(message)
                    })
                )

                pdf_bytes = output_path.read_bytes()

                events.put({
                    "type": "complete",
                    "filename": download_name,
                    "pdf_base64": base64.b64encode(
                        pdf_bytes
                    ).decode("ascii")
                })

        except Exception as exc:

            app.logger.exception("PDF processing failed")

            events.put({
                "type": "error",
                "message": (
                    f"Could not process this PDF: "
                    f"{type(exc).__name__}: {exc}"
                )
            })

        finally:
            events.put(None)

    def generate():

        yield json.dumps({
            "type": "log",
            "message": (
                "Starting PDF processing. Please keep this page open."
            )
        }) + "\n"

        thread = threading.Thread(
            target=worker,
            daemon=True
        )

        thread.start()

        while True:

            event = events.get()

            if event is None:
                break

            yield json.dumps(
                event,
                separators=(",", ":")
            ) + "\n"

    return Response(
        stream_with_context(generate()),
        mimetype="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@app.errorhandler(413)
def too_large(_error):
    return jsonify({
        "error": "File is too large. Maximum upload size is 20 MB."
    }), 413


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
